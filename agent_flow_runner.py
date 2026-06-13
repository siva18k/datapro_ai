"""Run multi-agent flows — chain agents with context handoff between steps."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from agent_runner import run_agent_events
from api.llm import generate_answer, resolve_llm_runtime
from catalog_db import get_agent, get_agent_flow


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
        elif sid == "report":
            if payload.get("summary"):
                parts.append(f"Report summary: {payload['summary']}")
            if payload.get("title"):
                parts.append(f"Report title: {payload['title']}")
        elif sid == "email" and payload.get("subject"):
            parts.append(f"Email subject: {payload['subject']}")
        elif msg and sid not in ("tools",):
            parts.append(msg)
    if not parts:
        return f"Agent «{agent_name}» completed with no detailed output."
    return "\n".join(parts)


def _build_handoff_instructions(
    flow_instructions: str,
    step_handoff: str,
    prior_context: str,
    step_index: int,
    total_steps: int,
) -> str:
    sections: list[str] = []
    if flow_instructions.strip():
        sections.append(f"## Flow instructions\n{flow_instructions.strip()}")
    if prior_context.strip():
        sections.append(f"## Output from previous agents in this flow\n{prior_context.strip()}")
    if step_handoff.strip():
        sections.append(f"## Handoff for this step\n{step_handoff.strip()}")
    sections.append(
        f"You are step {step_index + 1} of {total_steps} in a multi-agent flow. "
        "Use prior agent outputs above when relevant."
    )
    return "\n\n".join(sections)


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

    steps = flow.get("steps") or []
    if not steps:
        yield _error("Flow has no steps — add agents via drag-and-drop or @ mentions")
        return

    flow_instructions = (flow.get("instructions") or "").strip()
    extra = (extra_instructions or "").strip()
    if extra:
        flow_instructions = f"{flow_instructions}\n\n## Additional instructions\n{extra}" if flow_instructions else extra

    yield _status(f"Starting flow «{flow['name']}» ({len(steps)} steps)")

    llm_backend, llm_model, llm_base_url = resolve_llm_runtime(
        backend=backend,
        model=model,
        base_url=ollama_base_url,
    )

    prior_context_parts: list[str] = []
    flow_agent_results: list[dict[str, Any]] = []
    last_report_html: str | None = None

    for idx, step_def in enumerate(steps):
        agent_id = step_def.get("agent_id")
        handoff = (step_def.get("handoff") or "").strip()
        if not agent_id:
            yield _step(f"flow_step_{idx}", "Skipped — missing agent", status="warn")
            continue

        agent = get_agent(agent_id)
        if not agent:
            yield _step(
                f"flow_step_{idx}",
                f"Agent not found for step {idx + 1}",
                status="error",
                payload={"agent_id": agent_id},
            )
            continue
        if not agent.get("enabled", True):
            yield _step(
                f"flow_step_{idx}",
                f"Agent «{agent['name']}» is disabled",
                status="error",
                payload={"agent_id": agent_id, "agent_name": agent["name"]},
            )
            continue

        agent_slug = agent.get("slug") or agent_id
        step_prefix = f"{agent_slug}"
        prior_context = "\n\n".join(prior_context_parts)
        handoff_text = _build_handoff_instructions(
            flow_instructions,
            handoff,
            prior_context,
            idx,
            len(steps),
        )

        yield _status(f"Step {idx + 1}/{len(steps)}: running «{agent['name']}»…")
        yield _step(
            f"flow_step_{idx}_start",
            f"Starting agent «{agent['name']}»",
            payload={
                "agent_id": agent_id,
                "agent_name": agent["name"],
                "agent_slug": agent_slug,
                "step_index": idx,
                "handoff": handoff,
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
                    f"{step_prefix}:error",
                    agent_error,
                    status="error",
                    payload={"agent_id": agent_id, "agent_name": agent["name"]},
                )
                break
            if event["type"] == "status":
                yield _status(event.get("message", ""))
            elif event["type"] == "step":
                inner_id = event.get("step_id", "step")
                collected.append(event)
                yield _step(
                    f"{step_prefix}:{inner_id}",
                    event.get("message", ""),
                    status=event.get("status", "ok"),
                    payload={
                        **(event.get("payload") or {}),
                        "agent_id": agent_id,
                        "agent_name": agent["name"],
                        "agent_slug": agent_slug,
                        "flow_step_index": idx,
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
                    "completed_steps": idx,
                    "total_steps": len(steps),
                    "failed": True,
                    "error": agent_error,
                }
            )
            return

        summary = _summarize_agent_output(agent["name"], collected)
        prior_context_parts.append(f"### {agent['name']}\n{summary}")
        flow_agent_results.append(
            {
                "agent_id": agent_id,
                "agent_name": agent["name"],
                "agent_slug": agent_slug,
                "step_index": idx,
                "summary": summary,
                "result": agent_result,
            }
        )

        yield _step(
            f"flow_step_{idx}_done",
            f"Completed «{agent['name']}»",
            payload={
                "agent_id": agent_id,
                "agent_name": agent["name"],
                "summary": summary,
            },
        )

    yield _status("Flow complete")
    yield _result(
        {
            "flow_id": flow_id,
            "completed_steps": len(steps),
            "total_steps": len(steps),
            "failed": False,
            "agent_results": flow_agent_results,
            "report_html": last_report_html,
        }
    )
