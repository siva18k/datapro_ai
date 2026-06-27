"""Run configurable agents — KPI check, report generation, email preview."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from typing import Any

from agent_mcp_runner import (
    format_agent_mcp_context,
    mcp_summary_for_report,
    run_agent_mcp_enrichment,
)
from api.analytics_models import AnalyticsRequest
from api.analytics_runner import run_analytics_events
from api.ask_export import build_html_page
from api.llm import generate_answer, resolve_llm_runtime
from catalog_db import get_agent, parse_domain_slugs_from_instructions
from catalog_service import ensure_catalog_ready, resolve_domains


def _status(message: str) -> dict[str, Any]:
    return {"type": "status", "message": message}


def _step(step_id: str, message: str, *, status: str = "ok", payload: dict | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {"type": "step", "step_id": step_id, "message": message, "status": status}
    if payload:
        event["payload"] = payload
    return event


def _error(message: str) -> dict[str, Any]:
    return {"type": "error", "message": message}


def _result(payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": "result", "payload": payload}


def _smtp_configured() -> bool:
    host = os.environ.get("SMTP_HOST", "")
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", "")
    return bool(host and user and password and from_addr)


def _validate_domain_slugs(slugs: list[str]) -> tuple[list[dict], list[str]]:
    if not slugs:
        return [], []
    resolved = resolve_domains(slugs)
    found = {d["slug"] for d in resolved}
    unknown = [s for s in slugs if s not in found]
    return resolved, unknown


def _kpi_prompt_from_instructions(instructions: str) -> str:
    """Derive an analytics question for KPI evaluation."""
    return (
        "Based on the agent instructions below, write ONE concise analytics question "
        "that retrieves the metric needed to evaluate the KPI rules. "
        "Return only the question, no markdown fences.\n\n"
        f"{instructions}"
    )


def _instructions_want_chart(instructions: str) -> bool:
    """True when Report Output (or instructions) ask for a chart visualization."""
    match = re.search(r"##\s*report\s*output\b.*?(?=\n##|\Z)", instructions, re.I | re.S)
    section = (match.group(0) if match else instructions).lower()
    return bool(re.search(r"\bchart\b|\bvisuali[sz]", section))


def _kpi_pass_fail(instructions: str, summary: str, columns: list[str] | None, rows: list | None) -> tuple[bool, str]:
    prompt = (
        "You are evaluating whether KPI rules in agent instructions are met.\n\n"
        "## Agent instructions\n"
        f"{instructions}\n\n"
        "## Query result summary\n"
        f"{summary}\n\n"
    )
    if columns and rows:
        sample = rows[:5]
        prompt += f"Columns: {columns}\nSample rows: {json.dumps(sample, default=str)}\n\n"
    prompt += (
        "Reply with exactly two lines:\n"
        "PASS or FAIL\n"
        "One sentence explanation."
    )
    raw = generate_answer(prompt).strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    passed = lines[0].upper().startswith("PASS") if lines else False
    explanation = lines[1] if len(lines) > 1 else raw
    return passed, explanation


def run_agent_events(
    agent_id: str,
    embedder,
    *,
    extra_instructions: str | None = None,
    backend: str | None = None,
    model: str | None = None,
    ollama_base_url: str | None = None,
) -> Iterator[dict[str, Any]]:
    ensure_catalog_ready()
    agent = get_agent(agent_id)
    if not agent:
        yield _error("Agent not found")
        return
    if not agent.get("enabled", True):
        yield _error("Agent is disabled")
        return

    instructions = (agent.get("instructions") or "").strip()
    extra = (extra_instructions or "").strip()
    if extra:
        instructions = f"{instructions}\n\n## Additional instructions\n{extra}" if instructions else extra
    if not instructions:
        yield _error("Agent has no instructions")
        return

    caps = agent.get("capabilities") or {}
    kpi_check = bool(caps.get("kpi_check"))
    generate_report = bool(caps.get("generate_report"))
    send_email = bool(caps.get("send_email"))
    email_to = (caps.get("email_to") or "").strip()

    domain_slugs = parse_domain_slugs_from_instructions(instructions)
    resolved, unknown = _validate_domain_slugs(domain_slugs)
    if unknown:
        yield _error(f"Unknown domain slug(s) in instructions: {', '.join(unknown)}")
        return

    domain_names = ", ".join(d["name"] for d in resolved) if resolved else "Auto"
    yield _status(f"Running agent «{agent['name']}» — domains: {domain_names}")

    tools = agent.get("tools") or []

    llm_backend, llm_model, llm_base_url = resolve_llm_runtime(
        backend=backend,
        model=model,
        base_url=ollama_base_url,
    )

    mcp_enrichment = None
    mcp_context = ""
    if tools or resolved:
        yield _status("Loading MCP tools, resources, and prompts…")
        mcp_enrichment = run_agent_mcp_enrichment(
            instructions,
            agent_tools=tools,
            resolved_domains=resolved,
            model=llm_model,
            backend=llm_backend,
            base_url=llm_base_url,
        )
        mcp_context = format_agent_mcp_context(mcp_enrichment)
        if mcp_enrichment.trace:
            if tools:
                tool_list = ", ".join(
                    f"{t['server_name']}.{t['tool_name']}" for t in tools
                )
                yield _step(
                    "mcp_catalog",
                    f"Bound MCP tools: {tool_list}",
                    payload={"tools": tools},
                )
            for entry in mcp_enrichment.trace:
                kind = entry.get("kind")
                if kind == "tool":
                    tool = entry.get("tool", "tool")
                    source = entry.get("source") or entry.get("domain") or entry.get("server") or "mcp"
                    status = "warn" if entry.get("status") == "unreachable" else "ok"
                    yield _step(
                        f"mcp:{tool}",
                        f"MCP tool «{tool}» ({source})"
                        + (" — server unreachable" if status == "warn" else ""),
                        status=status,
                        payload=entry,
                    )
                elif kind == "resource":
                    yield _step(
                        "mcp:resource",
                        f"MCP resource «{entry.get('uri', 'resource')}»",
                        payload=entry,
                    )
                elif kind == "prompt":
                    yield _step(
                        f"mcp:prompt:{entry.get('prompt', 'prompt')}",
                        f"MCP prompt «{entry.get('prompt', 'prompt')}»",
                        payload=entry,
                    )
            yield _step(
                "mcp",
                f"MCP enrichment complete ({len(mcp_enrichment.tool_results)} tool result(s))",
                payload={
                    "reasoning": mcp_enrichment.reasoning,
                    "tool_count": len(mcp_enrichment.tool_results),
                    "resource_count": len(mcp_enrichment.resources),
                    "prompt_count": len(mcp_enrichment.prompt_results),
                },
            )
        elif tools:
            tool_list = ", ".join(f"{t['server_name']}.{t['tool_name']}" for t in tools)
            yield _step(
                "tools",
                f"Bound MCP tools: {tool_list} (no reachable MCP servers)",
                status="warn",
                payload={"tools": tools},
            )

    instructions_with_mcp = (
        f"{instructions}\n\n{mcp_context}" if mcp_context else instructions
    )

    yield _status("Planning workflow from instructions…")
    plan_prompt = (
        "Summarize the workflow steps for this agent in 3-6 bullet points. "
        f"Capabilities enabled: KPI check={kpi_check}, generate report={generate_report}, "
        f"send email={send_email}.\n\n## Instructions\n{instructions_with_mcp}"
    )
    plan_text = generate_answer(
        plan_prompt,
        model=llm_model,
        backend=llm_backend,
        base_url=llm_base_url,
    )
    yield _step("plan", "Workflow plan", payload={"plan": plan_text.strip()})

    kpi_passed: bool | None = None
    kpi_explanation = ""
    dash_data: dict[str, Any] | None = None

    if kpi_check:
        yield _status("Checking KPI against catalog data…")
        analytics_prompt = _kpi_prompt_from_instructions(instructions)
        domain_overrides = [d["slug"] for d in resolved] if resolved else None
        req = AnalyticsRequest(
            prompt=analytics_prompt,
            domain_overrides=domain_overrides,
            backend=backend,
            model=model,
            ollama_base_url=ollama_base_url,
        )
        for event in run_analytics_events(req, embedder):
            if event["type"] == "status":
                yield _status(event["message"])
            elif event["type"] == "result":
                dash_data = event["data"]
            elif event["type"] == "error":
                yield _step("kpi", event["message"], status="error")
                kpi_passed = False
                kpi_explanation = event["message"]

        if dash_data and kpi_passed is not False:
            summary = dash_data.get("summary") or ""
            columns = dash_data.get("columns")
            rows = dash_data.get("rows")
            kpi_passed, kpi_explanation = _kpi_pass_fail(
                instructions_with_mcp, summary, columns, rows
            )
            status = "ok" if kpi_passed else "warn"
            yield _step(
                "kpi",
                f"KPI {'passed' if kpi_passed else 'not met'}: {kpi_explanation}",
                status=status,
                payload={
                    "passed": kpi_passed,
                    "explanation": kpi_explanation,
                    "summary": summary,
                },
            )

    need_report = generate_report

    report_html: str | None = None
    if need_report:
        yield _status("Generating report…")
        if not dash_data:
            report_prompt = (
                "From the agent instructions, write one analytics question for the report data.\n\n"
                f"{instructions_with_mcp}"
            )
            domain_overrides = [d["slug"] for d in resolved] if resolved else None
            req = AnalyticsRequest(
                prompt=report_prompt,
                domain_overrides=domain_overrides,
                backend=backend,
                model=model,
                ollama_base_url=ollama_base_url,
            )
            for event in run_analytics_events(req, embedder):
                if event["type"] == "status":
                    yield _status(event["message"])
                elif event["type"] == "result":
                    dash_data = event["data"]
                elif event["type"] == "error":
                    yield _step("report", event["message"], status="error")
                    dash_data = None

        if dash_data:
            title = agent.get("name") or "Agent report"
            summary = dash_data.get("summary") or ""
            columns = dash_data.get("columns")
            rows = dash_data.get("rows")
            sql = dash_data.get("sql")
            report_html = build_html_page(
                question=title,
                answer=summary,
                columns=columns,
                rows=rows,
                sql=sql,
                domain_name=dash_data.get("domain_name"),
                include_chart=_instructions_want_chart(instructions),
            )
            yield _step(
                "report",
                "Report generated",
                payload={
                    "html": report_html,
                    "title": title,
                    "summary": summary,
                    "columns": columns,
                    "rows": rows,
                },
            )
        else:
            mcp_summary = mcp_summary_for_report(mcp_enrichment)
            if mcp_summary:
                title = agent.get("name") or "Agent report"
                report_html = build_html_page(
                    question=title,
                    answer=mcp_summary,
                    domain_name=domain_names if domain_names != "Auto" else None,
                    include_chart=_instructions_want_chart(instructions),
                )
                yield _step(
                    "report",
                    "Report generated from MCP context",
                    payload={
                        "html": report_html,
                        "title": title,
                        "summary": mcp_summary,
                        "source": "mcp",
                    },
                )
            else:
                yield _step("report", "Could not generate report — no data returned", status="warn")

    if send_email:
        yield _status("Preparing email preview…")
        subject = f"Report: {agent.get('name', 'Agent')}"
        body_summary = ""
        if dash_data:
            body_summary = dash_data.get("summary") or ""
        elif kpi_explanation:
            body_summary = kpi_explanation
        elif mcp_enrichment:
            body_summary = mcp_summary_for_report(mcp_enrichment) or plan_text[:500]
        else:
            body_summary = plan_text[:500]

        html_body = report_html or build_html_page(
            question=subject,
            answer=body_summary,
            domain_name=domain_names if domain_names != "Auto" else None,
        )
        smtp_ok = _smtp_configured()
        yield _step(
            "email",
            "Email preview (not sent)" if smtp_ok else "Email MCP not configured — would send:",
            status="display_only",
            payload={
                "to": email_to or "(set recipient in agent abilities)",
                "subject": subject,
                "html_body": html_body,
                "smtp_configured": smtp_ok,
                "sent": False,
            },
        )

    yield _result(
        {
            "agent_id": agent_id,
            "kpi_passed": kpi_passed,
            "report_generated": bool(report_html),
            "email_preview": send_email,
            "mcp_tool_results": len(mcp_enrichment.tool_results) if mcp_enrichment else 0,
        }
    )


def format_agent_instructions(instructions: str) -> str:
    prompt = (
        "Reformat the following agent instructions into well-structured markdown with sections: "
        "Goal, Domains, Steps, KPI rules, Report output, Notifications. "
        "Preserve `/domain-slug` tokens (e.g. /finance) and any tool references exactly. "
        "Markdown only, no code fences wrapping the whole document.\n\n"
        f"{instructions}"
    )
    return generate_answer(prompt).strip()


def warn_unknown_domain_slugs(instructions: str) -> list[str]:
    slugs = parse_domain_slugs_from_instructions(instructions)
    if not slugs:
        return []
    _, unknown = _validate_domain_slugs(slugs)
    return unknown
