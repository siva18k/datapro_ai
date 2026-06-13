from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_flow_runner import run_agent_flow_events
from api.deps import get_embedder
from catalog_db import (
    create_agent_flow,
    delete_agent_flow,
    get_agent_flow,
    list_agent_flows,
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
    steps: list[AgentFlowStep] = Field(default_factory=list)


class AgentFlowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    steps: list[AgentFlowStep] | None = None
    enabled: bool | None = None


class AgentFlowRunBody(BaseModel):
    extra_instructions: str | None = None
    backend: str | None = None
    model: str | None = None
    ollama_base_url: str | None = None


@router.get("")
def list_all():
    return list_agent_flows()


@router.post("")
def create(body: AgentFlowCreate):
    steps = [s.model_dump() for s in body.steps]
    return create_agent_flow(
        body.name,
        description=body.description,
        instructions=body.instructions,
        steps=steps,
    )


@router.get("/{flow_id}")
def get_one(flow_id: str):
    flow = get_agent_flow(flow_id)
    if not flow:
        raise HTTPException(404, "Agent flow not found")
    return flow


@router.patch("/{flow_id}")
def patch(flow_id: str, body: AgentFlowUpdate):
    if not get_agent_flow(flow_id):
        raise HTTPException(404, "Agent flow not found")
    data = body.model_dump(exclude_none=True)
    if "steps" in data and data["steps"] is not None:
        data["steps"] = [AgentFlowStep(**s).model_dump() if isinstance(s, dict) else s for s in data["steps"]]
    flow = update_agent_flow(flow_id, **data)
    if not flow:
        raise HTTPException(404, "Agent flow not found")
    return flow


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
