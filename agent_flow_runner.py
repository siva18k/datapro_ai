"""Run multi-agent flows — DAG execution with context handoff on connections."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from agent_flow_graph import incoming_edges, node_by_id, node_kind, node_label, normalize_flow_steps, topological_order
from agent_flow_lint import lint_flow
from agent_runner import run_agent_events
from api.llm import generate_answer, resolve_llm_runtime
from catalog_db import get_agent, get_agent_flow, list_agents


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


def _table_preview(columns: Any, rows: Any, *, max_rows: int = 40) -> str:
    if not columns or not rows:
        return ""
    try:
        preview = {
            "columns": list(columns),
            "rows": list(rows)[:max_rows],
            "row_count": len(rows),
            "truncated": len(rows) > max_rows,
        }
        return json.dumps(preview, default=str)
    except (TypeError, ValueError):
        return ""


def _summarize_agent_output(agent_name: str, collected: list[dict[str, Any]]) -> str:
    """Build a concise context block from an agent's emitted steps."""
    parts: list[str] = []
    for item in collected:
        sid = item.get("step_id", "")
        msg = item.get("message", "")
        payload = item.get("payload") or {}
        if sid == "plan" and payload.get("plan"):
            parts.append(f"Plan: {payload['plan']}")
        elif sid == "kpi":
            expl = payload.get("explanation") or msg
            passed = payload.get("passed")
            label = "passed" if passed else "not met"
            parts.append(f"KPI ({label}): {expl}")
            if payload.get("summary"):
                parts.append(f"KPI data summary: {payload['summary']}")
            table = _table_preview(payload.get("columns"), payload.get("rows"))
            if table:
                parts.append(f"KPI data table (JSON):\n{table}")
        elif sid == "report":
            if payload.get("summary"):
                parts.append(f"Report summary: {payload['summary']}")
            if payload.get("title"):
                parts.append(f"Report title: {payload['title']}")
            table = _table_preview(payload.get("columns"), payload.get("rows"))
            if table:
                parts.append(f"Report data table (JSON):\n{table}")
        elif sid == "email" and payload.get("subject"):
            parts.append(f"Email subject: {payload['subject']}")
        elif msg and sid not in ("tools",):
            parts.append(msg)
    if not parts:
        return f"Agent «{agent_name}» completed with no detailed output."
    return "\n".join(parts)


def _build_agent_extra_instructions(
    flow_goal: str,
    incoming_context: str,
    step_index: int,
    total_steps: int,
) -> str:
    sections: list[str] = []
    if flow_goal.strip():
        sections.append(
            "## Overall flow goal (context only)\n"
            f"{flow_goal.strip()}\n\n"
            "Do only this agent's job. Do not perform later flow steps "
            "(such as ranking, HTML, or formatting) unless they are already part of this agent's instructions."
        )
    if incoming_context.strip():
        sections.append(f"## Output from connected upstream steps\n{incoming_context.strip()}")
    sections.append(
        f"You are step {step_index + 1} of {total_steps} in a multi-step flow. "
        "Use upstream results when they are relevant to this agent."
    )
    return "\n\n".join(sections)


def _parse_task_json(raw: str) -> tuple[str, str | None]:
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            summary = str(parsed.get("summary") or "").strip() or raw.strip()
            html = parsed.get("html")
            html_s = str(html).strip() if html else None
            if html_s and "<" not in html_s:
                html_s = None
            return summary, html_s
    if "<table" in raw.lower() or "<html" in raw.lower():
        return "Custom step produced HTML output.", raw
    return raw.strip() or "Custom step completed with no text.", None


def _run_custom_task(
    *,
    title: str,
    instructions: str,
    flow_goal: str,
    incoming_context: str,
    step_index: int,
    total_steps: int,
    backend: str | None,
    model: str | None,
    ollama_base_url: str | None,
) -> tuple[str, str | None]:
    prompt = (
        f"You are custom flow step {step_index + 1} of {total_steps} named «{title}».\n"
        "Do only this step. Use upstream results as the data source when this step transforms prior output.\n\n"
        f"## This step's instructions\n{instructions.strip()}\n\n"
    )
    if flow_goal.strip():
        prompt += f"## Overall flow goal (context only — do not perform other steps)\n{flow_goal.strip()}\n\n"
    prompt += (
        "## Upstream results\n"
        f"{incoming_context.strip() or '(none — this is the first step; you have no prior data)'}\n\n"
        "If this step needs prior data and upstream results are empty, say clearly that the previous "
        "step did not pass data and what the user should connect.\n"
        "If the step asks for HTML, include a complete HTML fragment with a table and, if asked, "
        "a simple inline SVG or CSS bar chart.\n"
        'Return JSON only: {"summary": "plain-text or markdown result", "html": "optional html or null"}.'
    )
    raw = generate_answer(
        prompt,
        model=model,
        backend=backend,
        base_url=ollama_base_url,
    )
    return _parse_task_json(raw)


def _build_incoming_context(
    graph: dict[str, Any],
    node_id: str,
    node_outputs: dict[str, str],
    agent_names: dict[str, str],
) -> str:
    parts: list[str] = []
    for edge in incoming_edges(graph, node_id):
        parent_id = edge.get("from")
        if not parent_id:
            continue
        summary = node_outputs.get(parent_id)
        if not summary:
            continue
        parent_name = agent_names.get(parent_id, parent_id)
        handoff = (edge.get("handoff") or "").strip()
        block = f"### From {parent_name}\n{summary}"
        if handoff:
            block = f"### From {parent_name}\nHandoff: {handoff}\n{summary}"
        parts.append(block)
    return "\n\n".join(parts)


def run_agent_flow_events(
    flow_id: str,
    embedder,
    *,
    extra_instructions: str | None = None,
    backend: str | None = None,
    model: str | None = None,
    ollama_base_url: str | None = None,
) -> Iterator[dict[str, Any]]:
    flow = get_agent_flow(flow_id)
    if not flow:
        yield _error("Agent flow not found")
        return
    if not flow.get("enabled", True):
        yield _error("Agent flow is disabled")
        return

    graph = normalize_flow_steps(flow.get("steps"))
    nodes = graph.get("nodes") or []
    if not nodes:
        yield _error(
            "Flow has no steps on the canvas. Drag an agent into Flow steps, or add a Custom step. "
            "Text in Flow goal is not executed by itself."
        )
        return

    try:
        execution_order = topological_order(graph)
    except ValueError as exc:
        yield _error(str(exc))
        return

    flow_instructions = (flow.get("instructions") or "").strip()
    extra = (extra_instructions or "").strip()
    if extra:
        flow_instructions = (
            f"{flow_instructions}\n\n## Additional instructions\n{extra}" if flow_instructions else extra
        )

    known_slugs = {str(a.get("slug") or "").lower() for a in list_agents(enabled_only=True) if a.get("slug")}
    known_slugs.discard("")
    for warning in lint_flow(flow_instructions, graph, known_slugs=known_slugs):
        yield _step("flow_lint", warning, status="warn")

    total_steps = len(nodes)
    yield _status(f"Starting flow «{flow['name']}» ({total_steps} steps)")

    resolve_llm_runtime(
        backend=backend,
        model=model,
        base_url=ollama_base_url,
    )

    node_outputs: dict[str, str] = {}
    agent_names: dict[str, str] = {}
    flow_agent_results: list[dict[str, Any]] = []
    last_report_html: str | None = None
    completed = 0

    for step_index, node_id in enumerate(execution_order):
        node = node_by_id(graph, node_id)
        if not node:
            yield _step(node_id, "Skipped — missing node", status="warn")
            continue

        incoming_context = _build_incoming_context(graph, node_id, node_outputs, agent_names)
        kind = node_kind(node)

        if kind == "task":
            title = node_label(node)
            task_instructions = (node.get("instructions") or "").strip()
            agent_names[node_id] = title
            if not task_instructions:
                message = (
                    f"Custom step «{title}» has no instructions. "
                    "Open the flow editor, write what this step should do, save, and run again."
                )
                yield _step(f"{node_id}:error", message, status="error", payload={"node_id": node_id})
                yield _result(
                    {
                        "flow_id": flow_id,
                        "completed_steps": completed,
                        "total_steps": total_steps,
                        "failed": True,
                        "error": message,
                    }
                )
                return
            if step_index > 0 and not incoming_context.strip():
                yield _step(
                    f"{node_id}_data",
                    "This custom step has no connected upstream result. "
                    "Connect it from the previous step so it can use that data.",
                    status="warn",
                    payload={"node_id": node_id},
                )

            yield _status(f"Step {step_index + 1}/{total_steps}: custom step «{title}»…")
            yield _step(
                f"{node_id}_start",
                f"Starting custom step «{title}»",
                payload={"node_id": node_id, "step_index": step_index, "kind": "task"},
            )
            try:
                summary, html = _run_custom_task(
                    title=title,
                    instructions=task_instructions,
                    flow_goal=flow_instructions,
                    incoming_context=incoming_context,
                    step_index=step_index,
                    total_steps=total_steps,
                    backend=backend,
                    model=model,
                    ollama_base_url=ollama_base_url,
                )
            except Exception as exc:
                message = f"Custom step «{title}» failed: {exc}"
                yield _step(f"{node_id}:error", message, status="error")
                yield _result(
                    {
                        "flow_id": flow_id,
                        "completed_steps": completed,
                        "total_steps": total_steps,
                        "failed": True,
                        "error": message,
                    }
                )
                return

            if html:
                last_report_html = html
            node_outputs[node_id] = summary
            completed += 1
            flow_agent_results.append(
                {
                    "agent_id": "",
                    "agent_name": title,
                    "agent_slug": "",
                    "kind": "task",
                    "node_id": node_id,
                    "step_index": step_index,
                    "summary": summary,
                }
            )
            yield _step(
                f"{node_id}_done",
                f"Completed custom step «{title}»",
                payload={"node_id": node_id, "summary": summary, "html": html},
            )
            continue

        agent_id = node.get("agent_id")
        if not agent_id:
            yield _step(node_id, "Skipped — this step is not an agent or custom step", status="warn")
            continue

        agent = get_agent(agent_id)
        if not agent:
            yield _step(
                node_id,
                "Agent not found for this step. Remove it from the canvas or pick another agent.",
                status="error",
                payload={"agent_id": agent_id, "node_id": node_id},
            )
            yield _result(
                {
                    "flow_id": flow_id,
                    "completed_steps": completed,
                    "total_steps": total_steps,
                    "failed": True,
                    "error": "Agent not found for this step",
                }
            )
            return
        if not agent.get("enabled", True):
            message = f"Agent «{agent['name']}» is disabled"
            yield _step(
                node_id,
                message,
                status="error",
                payload={"agent_id": agent_id, "agent_name": agent["name"], "node_id": node_id},
            )
            yield _result(
                {
                    "flow_id": flow_id,
                    "completed_steps": completed,
                    "total_steps": total_steps,
                    "failed": True,
                    "error": message,
                }
            )
            return

        agent_slug = agent.get("slug") or agent_id
        agent_names[node_id] = agent["name"]
        handoff_text = _build_agent_extra_instructions(
            flow_instructions,
            incoming_context,
            step_index,
            total_steps,
        )

        yield _status(f"Step {step_index + 1}/{total_steps}: running «{agent['name']}»…")
        yield _step(
            f"{node_id}_start",
            f"Starting agent «{agent['name']}»",
            payload={
                "agent_id": agent_id,
                "agent_name": agent["name"],
                "agent_slug": agent_slug,
                "node_id": node_id,
                "step_index": step_index,
            },
        )

        collected: list[dict[str, Any]] = []
        agent_error: str | None = None
        agent_result: dict[str, Any] | None = None

        for event in run_agent_events(
            agent_id,
            embedder,
            extra_instructions=handoff_text,
            backend=backend,
            model=model,
            ollama_base_url=ollama_base_url,
        ):
            if event["type"] == "error":
                agent_error = event.get("message", "Agent error")
                yield _step(
                    f"{agent_slug}:error",
                    agent_error,
                    status="error",
                    payload={"agent_id": agent_id, "agent_name": agent["name"], "node_id": node_id},
                )
                break
            if event["type"] == "status":
                yield _status(event.get("message", ""))
            elif event["type"] == "step":
                inner_id = event.get("step_id", "step")
                collected.append(event)
                yield _step(
                    f"{agent_slug}:{inner_id}",
                    event.get("message", ""),
                    status=event.get("status", "ok"),
                    payload={
                        **(event.get("payload") or {}),
                        "agent_id": agent_id,
                        "agent_name": agent["name"],
                        "agent_slug": agent_slug,
                        "node_id": node_id,
                        "flow_step_index": step_index,
                    },
                )
                if inner_id == "report" and event.get("payload", {}).get("html"):
                    last_report_html = str(event["payload"]["html"])
            elif event["type"] == "result":
                agent_result = event.get("payload") or {}

        if agent_error:
            yield _result(
                {
                    "flow_id": flow_id,
                    "completed_steps": completed,
                    "total_steps": total_steps,
                    "failed": True,
                    "error": agent_error,
                }
            )
            return

        summary = _summarize_agent_output(agent["name"], collected)
        node_outputs[node_id] = summary
        completed += 1
        flow_agent_results.append(
            {
                "agent_id": agent_id,
                "agent_name": agent["name"],
                "agent_slug": agent_slug,
                "kind": "agent",
                "node_id": node_id,
                "step_index": step_index,
                "summary": summary,
                "result": agent_result,
            }
        )

        yield _step(
            f"{node_id}_done",
            f"Completed «{agent['name']}»",
            payload={
                "agent_id": agent_id,
                "agent_name": agent["name"],
                "node_id": node_id,
                "summary": summary,
            },
        )

    yield _status("Flow complete")
    yield _result(
        {
            "flow_id": flow_id,
            "completed_steps": completed,
            "total_steps": total_steps,
            "failed": False,
            "agent_results": flow_agent_results,
            "report_html": last_report_html,
        }
    )
