from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from agent_flow_graph import normalize_flow_steps, validate_graph
from agent_flow_lint import lint_flow
from agent_flow_runner import run_agent_flow_events
from api.deps import get_embedder
from catalog_db import (
    create_agent_flow,
    delete_agent_flow,
    get_agent_flow,
    list_agent_flows,
    list_agents,
    update_agent_flow,
)

router = APIRouter(prefix="/agent-flows", tags=["agent-flows"])


class AgentFlowStep(BaseModel):
    agent_id: str
    handoff: str = ""


class AgentFlowCreate(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    steps: Any = Field(default_factory=list)

    @field_validator("steps", mode="before")
    @classmethod
    def accept_graph_or_linear_steps(cls, value: Any) -> Any:
        if value is None or isinstance(value, (dict, list)):
            return value
        raise ValueError("steps must be a list or graph object")


class AgentFlowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    steps: Any | None = None
    enabled: bool | None = None

    @field_validator("steps", mode="before")
    @classmethod
    def accept_graph_or_linear_steps(cls, value: Any) -> Any:
        if value is None or isinstance(value, (dict, list)):
            return value
        raise ValueError("steps must be a list or graph object")


class AgentFlowRunBody(BaseModel):
    extra_instructions: str | None = None
    backend: str | None = None
    model: str | None = None
    ollama_base_url: str | None = None


def _known_agent_slugs() -> set[str]:
    return {str(a.get("slug") or "").lower() for a in list_agents(enabled_only=True) if a.get("slug")}


def _with_lint(flow: dict[str, Any] | None) -> dict[str, Any] | None:
    if not flow:
        return flow
    flow = dict(flow)
    flow["lint_warnings"] = lint_flow(
        flow.get("instructions") or "",
        flow.get("steps"),
        known_slugs=_known_agent_slugs(),
    )
    return flow


def _normalize_steps_payload(steps: list[AgentFlowStep] | dict[str, Any] | None) -> dict[str, Any]:
    if steps is None:
        return normalize_flow_steps([])
    if isinstance(steps, dict):
        graph = normalize_flow_steps(steps)
    else:
        graph = normalize_flow_steps([s.model_dump() if isinstance(s, AgentFlowStep) else s for s in steps])
    ok, message = validate_graph(graph)
    if not ok:
        raise HTTPException(400, message)
    return graph


@router.get("")
def list_all():
    return [_with_lint(flow) for flow in list_agent_flows()]


@router.post("")
def create(body: AgentFlowCreate):
    steps = _normalize_steps_payload(body.steps)
    return _with_lint(
        create_agent_flow(
            body.name,
            description=body.description,
            instructions=body.instructions,
            steps=steps,
        )
    )


@router.get("/{flow_id}")
def get_one(flow_id: str):
    flow = get_agent_flow(flow_id)
    if not flow:
        raise HTTPException(404, "Agent flow not found")
    return _with_lint(flow)


@router.patch("/{flow_id}")
def patch(flow_id: str, body: AgentFlowUpdate):
    if not get_agent_flow(flow_id):
        raise HTTPException(404, "Agent flow not found")
    data = body.model_dump(exclude_none=True)
    if "steps" in data and data["steps"] is not None:
        data["steps"] = _normalize_steps_payload(data["steps"])
    flow = update_agent_flow(flow_id, **data)
    if not flow:
        raise HTTPException(404, "Agent flow not found")
    return _with_lint(flow)


@router.delete("/{flow_id}")
def remove(flow_id: str):
    if not delete_agent_flow(flow_id):
        raise HTTPException(404, "Agent flow not found")
    return {"deleted": True, "id": flow_id}


@router.post("/{flow_id}/run/stream")
def run_stream(flow_id: str, body: AgentFlowRunBody):
    embedder = get_embedder()

    def generate():
        try:
            for event in run_agent_flow_events(
                flow_id,
                embedder,
                extra_instructions=body.extra_instructions,
                backend=body.backend,
                model=body.model,
                ollama_base_url=body.ollama_base_url,
            ):
                yield json.dumps(event, default=str) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
