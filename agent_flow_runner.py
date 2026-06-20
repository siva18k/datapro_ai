"""Run multi-agent flows — DAG execution with context handoff on connections."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from agent_flow_graph import incoming_edges, node_by_id, normalize_flow_steps, topological_order
from agent_runner import run_agent_events
from api.llm import resolve_llm_runtime
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
    incoming_context: str,
    step_index: int,
    total_steps: int,
) -> str:
    sections: list[str] = []
    if flow_instructions.strip():
        sections.append(f"## Flow instructions\n{flow_instructions.strip()}")
    if incoming_context.strip():
        sections.append(f"## Output from connected upstream agents\n{incoming_context.strip()}")
    sections.append(
        f"You are step {step_index + 1} of {total_steps} in a multi-agent flow. "
        "Use upstream agent outputs above when relevant."
    )
    return "\n\n".join(sections)


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
        yield _error("Flow has no steps — add agents via drag-and-drop or @ mentions")
        return

    try:
        execution_order = topological_order(graph)
    except ValueError as exc:
        yield _error(str(exc))
        return

    flow_instructions = (flow.get("instructions") or "").strip()
    extra = (extra_instructions or "").strip()
    if extra:
        flow_instructions = f"{flow_instructions}\n\n## Additional instructions\n{extra}" if flow_instructions else extra

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

        agent_id = node.get("agent_id")
        if not agent_id:
            yield _step(node_id, "Skipped — missing agent", status="warn")
            continue

        agent = get_agent(agent_id)
        if not agent:
            yield _step(
                node_id,
                "Agent not found for this step",
                status="error",
                payload={"agent_id": agent_id, "node_id": node_id},
            )
            continue
        if not agent.get("enabled", True):
            yield _step(
                node_id,
                f"Agent «{agent['name']}» is disabled",
                status="error",
                payload={"agent_id": agent_id, "agent_name": agent["name"], "node_id": node_id},
            )
            continue

        agent_slug = agent.get("slug") or agent_id
        agent_names[node_id] = agent["name"]
        incoming_context = _build_incoming_context(graph, node_id, node_outputs, agent_names)
        handoff_text = _build_handoff_instructions(
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
