from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_runner import format_agent_instructions, run_agent_events, warn_unknown_domain_slugs
from api.deps import get_embedder
from catalog_db import (
    create_agent,
    delete_agent,
    get_agent,
    list_agents,
    set_agent_tools,
    update_agent,
)

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    capabilities: dict[str, Any] = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    capabilities: dict[str, Any] | None = None
    enabled: bool | None = None


class AgentToolBinding(BaseModel):
    mcp_server_id: str
    tool_name: str


class AgentToolsUpdate(BaseModel):
    tools: list[AgentToolBinding] = Field(default_factory=list)


class FormatBody(BaseModel):
    instructions: str | None = None


class AgentRunBody(BaseModel):
    extra_instructions: str | None = None
    backend: str | None = None
    model: str | None = None
    ollama_base_url: str | None = None


def _agent_response(agent: dict) -> dict:
    warnings = warn_unknown_domain_slugs(agent.get("instructions") or "")
    out = dict(agent)
    if warnings:
        out["domain_warnings"] = warnings
    return out


@router.get("")
def list_all_agents():
    return [_agent_response(a) for a in list_agents()]


@router.post("")
def create(body: AgentCreate):
    agent = create_agent(
        body.name,
        description=body.description,
        instructions=body.instructions,
        capabilities=body.capabilities,
    )
    return _agent_response(agent)


@router.get("/{agent_id}")
def get_one(agent_id: str):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return _agent_response(agent)


@router.patch("/{agent_id}")
def patch(agent_id: str, body: AgentUpdate):
    if not get_agent(agent_id):
        raise HTTPException(404, "Agent not found")
    agent = update_agent(agent_id, **body.model_dump(exclude_none=True))
    if not agent:
        raise HTTPException(404, "Agent not found")
    return _agent_response(agent)


@router.delete("/{agent_id}")
def remove(agent_id: str):
    if not delete_agent(agent_id):
        raise HTTPException(404, "Agent not found")
    return {"deleted": True, "id": agent_id}


@router.put("/{agent_id}/tools")
def replace_tools(agent_id: str, body: AgentToolsUpdate):
    if not get_agent(agent_id):
        raise HTTPException(404, "Agent not found")
    tools = set_agent_tools(agent_id, [t.model_dump() for t in body.tools])
    agent = get_agent(agent_id)
    return {"ok": True, "tools": tools, "agent": _agent_response(agent)}


@router.post("/{agent_id}/format")
def format_instructions(agent_id: str, body: FormatBody):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    source = body.instructions if body.instructions is not None else agent.get("instructions") or ""
    if not source.strip():
        raise HTTPException(400, "No instructions to format")
    markdown = format_agent_instructions(source)
    return {"markdown": markdown}


@router.post("/{agent_id}/run/stream")
def run_stream(agent_id: str, body: AgentRunBody):
    embedder = get_embedder()

    def generate():
        try:
            for event in run_agent_events(
                agent_id,
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
