from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from catalog_db import list_domains, list_mcp_bindings, set_mcp_binding
from mcp_client import get_default_mcp_url, get_prompt_preview, list_server_capabilities, read_resource_preview
from mcp_process import get_server_log_tail, get_server_status, restart_server, start_server, stop_server
from mcp_registry import (
    REGISTRY_DEFAULTS,
    REGISTRY_PATH,
    get_prompt_meta,
    get_resource_meta,
    get_tool_description,
    get_tool_implementation,
    is_enabled,
    load_registry,
    save_registry,
)

router = APIRouter(prefix="/mcp", tags=["mcp"])


class McpBindingUpdate(BaseModel):
    domain_id: str
    capability_type: str
    capability_name: str
    enabled: bool
    source_id: str | None = None


class McpPromptUpdate(BaseModel):
    description: str | None = None
    template: str | None = None
    enabled: bool | None = None


class McpPromptPreviewBody(BaseModel):
    arguments: dict[str, str] | None = None


class McpResourcePreviewBody(BaseModel):
    uri: str
    params: dict[str, str] | None = None


def _resource_uri_parameters(uri_template: str) -> list[str]:
    return re.findall(r"\{(\w+)\}", uri_template)


def _resolve_resource_uri(uri_template: str, params: dict[str, str] | None) -> str:
    params = params or {}
    resolved = uri_template
    for key in _resource_uri_parameters(uri_template):
        if key not in params or not str(params[key]).strip():
            raise HTTPException(
                400,
                f"Missing parameter {key!r} for resource URI {uri_template}",
            )
        resolved = resolved.replace("{" + key + "}", str(params[key]).strip())
    return resolved


def _binding_enabled(
    bindings: list[dict],
    domain_id: str,
    capability_type: str,
    capability_name: str,
    *,
    source_id: str | None = None,
) -> bool:
    for row in bindings:
        if (
            row.get("domain_id") == domain_id
            and row.get("source_id") == source_id
            and row.get("capability_type") == capability_type
            and row.get("capability_name") == capability_name
        ):
            return bool(row.get("enabled", True))
    return True


def _status_payload(registry: dict | None = None) -> dict:
    registry = registry or load_registry()
    status = get_server_status(registry)
    return {
        **status,
        "default_url": get_default_mcp_url(),
        "server": registry.get("server", {}),
    }


@router.get("/status")
def mcp_status():
    return _status_payload()


@router.post("/start")
def mcp_start():
    registry = load_registry()
    ok, message = start_server(registry)
    return {"ok": ok, "message": message, **_status_payload(registry)}


@router.post("/stop")
def mcp_stop():
    registry = load_registry()
    ok, message = stop_server(registry)
    return {"ok": ok, "message": message, **_status_payload(registry)}


@router.post("/restart")
def mcp_restart():
    registry = load_registry()
    ok, message = restart_server(registry)
    return {"ok": ok, "message": message, **_status_payload(registry)}


@router.get("/capabilities")
def mcp_capabilities():
    registry = load_registry()
    status = get_server_status(registry)
    if not status["reachable"]:
        raise HTTPException(503, "MCP server is not reachable")
    try:
        return list_server_capabilities(status["url"])
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/log")
def mcp_log(lines: int = Query(default=80, ge=1, le=500)):
    return {"log": get_server_log_tail(max_lines=lines)}


@router.get("/resources/meta")
def mcp_resource_meta(uri: str = Query(..., min_length=1)):
    if uri not in REGISTRY_DEFAULTS["resources"]:
        raise HTTPException(404, f"Unknown resource: {uri}")
    registry = load_registry()
    meta = get_resource_meta(uri, registry)
    return {
        "uri": uri,
        "parameters": _resource_uri_parameters(uri),
        **meta,
    }


@router.post("/resources/preview")
def mcp_resource_preview(body: McpResourcePreviewBody):
    if body.uri not in REGISTRY_DEFAULTS["resources"]:
        raise HTTPException(404, f"Unknown resource: {body.uri}")
    registry = load_registry()
    status = get_server_status(registry)
    if not status["reachable"]:
        raise HTTPException(503, "MCP server is not reachable — start it to preview resources.")
    try:
        resolved = _resolve_resource_uri(body.uri, body.params)
        content = read_resource_preview(status["url"], resolved)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    max_len = 50_000
    truncated = len(content) > max_len
    return {
        "uri_template": body.uri,
        "uri": resolved,
        "content": content[:max_len],
        "truncated": truncated,
        "mime_type": get_resource_meta(body.uri, registry).get("mime_type"),
    }


@router.get("/tools/{name}")
def mcp_tool_detail(name: str):
    if name not in REGISTRY_DEFAULTS["tools"]:
        raise HTTPException(404, f"Unknown tool: {name}")
    registry = load_registry()
    detail: dict = {
        "name": name,
        "description": get_tool_description(name, registry),
        "enabled_in_registry": is_enabled("tools", name, registry),
        "implementation": get_tool_implementation(name),
        "implementation_path": "mcp_server.py",
        "input_schema": None,
        "output_schema": None,
        "live_description": None,
    }
    status = get_server_status(registry)
    if status["reachable"]:
        try:
            caps = list_server_capabilities(status["url"])
            live = next((t for t in caps.get("tools", []) if t.get("name") == name), None)
            if live:
                detail["input_schema"] = live.get("inputSchema")
                detail["output_schema"] = live.get("outputSchema")
                detail["live_description"] = live.get("description")
        except Exception:
            pass
    return detail


@router.get("/registry")
def mcp_registry():
    registry = load_registry()
    tools = []
    for name in REGISTRY_DEFAULTS["tools"]:
        entry = registry.get("tools", {}).get(name, {})
        defaults = REGISTRY_DEFAULTS["tools"][name]
        tools.append(
            {
                "name": name,
                "description": entry.get("description", defaults["description"]),
                "enabled": entry.get("enabled", defaults.get("enabled", True)),
            }
        )
    resources = []
    for uri in REGISTRY_DEFAULTS["resources"]:
        meta = get_resource_meta(uri, registry)
        resources.append({"uri": uri, **meta})
    prompts = []
    for name in REGISTRY_DEFAULTS["prompts"]:
        meta = get_prompt_meta(name, registry)
        prompts.append({"name": name, **meta})
    return {
        "registry_path": str(REGISTRY_PATH),
        "server": registry.get("server", {}),
        "tools": tools,
        "resources": resources,
        "prompts": prompts,
    }


@router.put("/registry/prompts/{name}")
def update_registry_prompt(name: str, body: McpPromptUpdate):
    if name not in REGISTRY_DEFAULTS["prompts"]:
        raise HTTPException(404, f"Unknown prompt: {name}")
    registry = load_registry()
    entry = registry.setdefault("prompts", {}).setdefault(name, {})
    if body.description is not None:
        entry["description"] = body.description
    if body.template is not None:
        entry["template"] = body.template
    if body.enabled is not None:
        entry["enabled"] = body.enabled
    save_registry(registry)
    return {
        "ok": True,
        "requires_restart": True,
        "prompt": {"name": name, **get_prompt_meta(name, registry)},
    }


@router.post("/prompts/{name}/preview")
def preview_prompt(name: str, body: McpPromptPreviewBody | None = None):
    if name not in REGISTRY_DEFAULTS["prompts"]:
        raise HTTPException(404, f"Unknown prompt: {name}")
    registry = load_registry()
    status = get_server_status(registry)
    if not status["reachable"]:
        raise HTTPException(503, "MCP server is not reachable — start it to preview live prompts.")
    try:
        preview = get_prompt_preview(status["url"], name, (body.arguments if body else None) or {})
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"preview": preview}


@router.get("/binding-catalog")
def binding_catalog():
    """Default capability names grouped by type (for domain binding UI)."""
    return {
        "tools": list(REGISTRY_DEFAULTS["tools"].keys()),
        "resources": list(REGISTRY_DEFAULTS["resources"].keys()),
        "prompts": list(REGISTRY_DEFAULTS["prompts"].keys()),
    }


@router.get("/bindings")
def mcp_bindings(domain_id: str):
    if not any(d["id"] == domain_id for d in list_domains(enabled_only=False)):
        raise HTTPException(404, "Domain not found")
    bindings = list_mcp_bindings(domain_id)
    result: dict[str, list[dict]] = {"tools": [], "resources": [], "prompts": []}
    for name in REGISTRY_DEFAULTS["tools"]:
        result["tools"].append(
            {
                "name": name,
                "enabled": _binding_enabled(bindings, domain_id, "tool", name),
                "description": get_tool_description(name),
            }
        )
    for uri in REGISTRY_DEFAULTS["resources"]:
        meta = get_resource_meta(uri)
        result["resources"].append(
            {
                "name": meta["name"],
                "uri": uri,
                "enabled": _binding_enabled(bindings, domain_id, "resource", meta["name"]),
                "description": meta["description"],
            }
        )
    for name in REGISTRY_DEFAULTS["prompts"]:
        meta = get_prompt_meta(name)
        result["prompts"].append(
            {
                "name": name,
                "enabled": _binding_enabled(bindings, domain_id, "prompt", name),
                "description": meta["description"],
            }
        )
    return {"domain_id": domain_id, "bindings": result}


@router.put("/bindings")
def update_binding(body: McpBindingUpdate):
    if body.capability_type not in ("tool", "resource", "prompt"):
        raise HTTPException(400, "capability_type must be tool, resource, or prompt")
    set_mcp_binding(
        body.domain_id,
        body.capability_type,
        body.capability_name,
        body.enabled,
        source_id=body.source_id,
    )
    return {"ok": True, "requires_restart": True}
