from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from catalog_db import (
    add_mcp_binding,
    create_mcp_server,
    delete_mcp_server,
    get_domain,
    get_domain_prompt,
    get_mcp_server,
    list_domains,
    list_mcp_bindings,
    list_mcp_servers,
    list_dismissed_optional_mcp_servers,
    remove_mcp_binding,
    restore_optional_mcp_server,
    set_mcp_binding,
    update_mcp_server,
)
from domain_prompt_service import (
    is_local_prompt_name,
    local_prompt_slug,
    prompt_template_parameters,
    render_domain_local_prompt,
)
from mcp_client import check_mcp_server, get_default_mcp_url, get_prompt_preview, list_server_capabilities, read_resource_preview
from integration_mcp_process import enrich_server_runtime, start_integration, stop_integration
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
    mcp_server_id: str | None = None


class McpBindingAdd(BaseModel):
    domain_id: str
    mcp_server_id: str
    capability_type: str
    capability_name: str


class McpServerCreate(BaseModel):
    name: str
    url: str
    description: str = ""
    server_kind: str = "public"
    transport: str = "streamable-http"


class McpServerUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    description: str | None = None
    server_kind: str | None = None
    transport: str | None = None
    enabled: bool | None = None


class McpPromptUpdate(BaseModel):
    description: str | None = None
    template: str | None = None
    enabled: bool | None = None


class McpPromptPreviewBody(BaseModel):
    arguments: dict[str, str] | None = None
    domain_id: str | None = None


class McpResourcePreviewBody(BaseModel):
    uri: str
    params: dict[str, str] | None = None
    domain_id: str | None = None


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


def _mcp_client_error_message(exc: BaseException) -> str:
    """Surface MCP client failures without opaque TaskGroup wrappers."""
    from mcp.shared.exceptions import McpError

    if isinstance(exc, McpError):
        return str(exc)
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            msg = _mcp_client_error_message(sub)
            if msg:
                return msg
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause and cause is not exc:
        return _mcp_client_error_message(cause)
    return str(exc)


_BUILTIN_PROMPT_ARGUMENTS: dict[str, list[str]] = {
    "citation_rules": [],
    "grounded_answer": ["question", "top_k"],
    "summarize_document": ["source_file"],
    "domain_grounded_answer": ["question", "domain", "top_k"],
    "domain_sql_context": [
        "question",
        "domain_name",
        "schema",
        "calendar",
        "glossary",
        "sql_notes",
        "tool_context",
    ],
}

_DOMAIN_CONTEXT_PROMPT_ARGS: dict[str, frozenset[str]] = {
    "domain_grounded_answer": frozenset({"domain"}),
    "domain_sql_context": frozenset(
        {"domain_name", "schema", "calendar", "glossary", "sql_notes", "tool_context"}
    ),
}

_SAMPLE_PROMPT_QUESTION = "What datasets and tables are in this domain?"
_SAMPLE_SUMMARIZE_SOURCE = "travel_policy.md"


def _prompt_arguments_from_live(registry: dict, name: str) -> list[str]:
    status = get_server_status(registry)
    if status["reachable"]:
        try:
            caps = list_server_capabilities(status["url"])
            for prompt in caps.get("prompts", []):
                if prompt.get("name") == name:
                    return [arg["name"] for arg in prompt.get("arguments", []) if arg.get("name")]
        except Exception:
            pass
    return list(_BUILTIN_PROMPT_ARGUMENTS.get(name, []))


def _build_prompt_preview_arguments(
    name: str,
    domain_id: str | None,
    user_args: dict[str, str] | None,
) -> dict[str, str]:
    args = {key: str(value).strip() for key, value in (user_args or {}).items() if str(value).strip()}

    if name == "grounded_answer":
        args.setdefault("question", _SAMPLE_PROMPT_QUESTION)
        args.setdefault("top_k", "3")
    elif name == "summarize_document":
        args.setdefault("source_file", _SAMPLE_SUMMARIZE_SOURCE)

    if domain_id:
        from catalog_db import get_domain

        row = get_domain(domain_id=domain_id) or {}
        slug = str(row.get("slug") or "").strip()
        domain_name = str(row.get("name") or slug or "Domain").strip()
        if name == "domain_grounded_answer":
            args.setdefault("question", _SAMPLE_PROMPT_QUESTION)
            args.setdefault("top_k", "3")
            if slug:
                args.setdefault("domain", slug)
        elif name == "domain_sql_context":
            from mcp_reference_service import gather_domain_reference_texts

            refs = gather_domain_reference_texts(domain_id, domain_slug=slug or None)
            args.setdefault("question", _SAMPLE_PROMPT_QUESTION)
            args.setdefault("domain_name", domain_name)
            args.setdefault("schema", refs.get("schema", "")[:8000])
            args.setdefault("calendar", refs.get("calendar", "")[:4000])
            args.setdefault("glossary", refs.get("glossary", "")[:4000])
            args.setdefault("sql_notes", refs.get("sql_notes", "")[:4000])
            args.setdefault("tool_context", "(none)")

    return args


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
    return False


def _group_bindings(bindings: list[dict], *, domain_id: str | None = None) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {"tools": [], "resources": [], "prompts": []}
    type_key = {"tool": "tools", "resource": "resources", "prompt": "prompts"}
    for row in bindings:
        if row.get("source_id"):
            continue
        key = type_key.get(row.get("capability_type", ""))
        if not key:
            continue
        cap_name = row.get("capability_name") or ""
        display_name = cap_name
        item = {
            "id": row.get("id"),
            "name": display_name,
            "capability_name": cap_name,
            "enabled": bool(row.get("enabled", True)),
            "mcp_server_id": row.get("mcp_server_id"),
            "server_name": row.get("server_name"),
            "server_slug": row.get("server_slug"),
            "server_url": row.get("server_url"),
            "server_kind": row.get("server_kind"),
            "prompt_kind": "global",
        }
        if key == "prompts" and is_local_prompt_name(cap_name) and domain_id:
            slug = local_prompt_slug(cap_name)
            local = get_domain_prompt(domain_id, slug=slug)
            item["prompt_kind"] = "local"
            item["local_slug"] = slug
            if local:
                item["name"] = local["name"]
                item["description"] = local.get("description") or ""
                item["local_prompt_id"] = local["id"]
        grouped[key].append(item)
    return grouped


def _builtin_capabilities(registry: dict) -> dict:
    tools = []
    for name in REGISTRY_DEFAULTS["tools"]:
        tools.append(
            {
                "name": name,
                "description": get_tool_description(name, registry),
            }
        )
    resources = []
    for uri in REGISTRY_DEFAULTS["resources"]:
        meta = get_resource_meta(uri, registry)
        resources.append({"name": meta["name"], "uri": uri, "description": meta["description"]})
    prompts = []
    for name in REGISTRY_DEFAULTS["prompts"]:
        meta = get_prompt_meta(name, registry)
        prompts.append({"name": name, "description": meta["description"]})
    return {"tools": tools, "resources": resources, "prompts": prompts}


def _live_capabilities_for_server(server: dict, registry: dict | None = None) -> dict:
    registry = registry or load_registry()
    reachable = check_mcp_server(server["url"])
    out = {"reachable": reachable, "tools": [], "resources": [], "prompts": []}
    if server.get("is_builtin"):
        builtin = _builtin_capabilities(registry)
        out["tools"] = builtin["tools"]
        out["resources"] = builtin["resources"]
        out["prompts"] = builtin["prompts"]
    if reachable:
        try:
            live = list_server_capabilities(server["url"])
            if not server.get("is_builtin"):
                out["tools"] = [
                    {"name": t.get("name"), "description": t.get("description", "")}
                    for t in live.get("tools", [])
                    if t.get("name")
                ]
                out["resources"] = [
                    {"name": r.get("name") or r.get("uri"), "uri": r.get("uri"), "description": r.get("description", "")}
                    for r in live.get("resources", [])
                    if r.get("uri")
                ]
                out["prompts"] = [
                    {"name": p.get("name"), "description": p.get("description", "")}
                    for p in live.get("prompts", [])
                    if p.get("name")
                ]
            else:
                live_tools = {t.get("name"): t for t in live.get("tools", [])}
                live_resources = {r.get("uri"): r for r in live.get("resources", [])}
                live_prompts = {p.get("name"): p for p in live.get("prompts", [])}
                for tool in out["tools"]:
                    live = live_tools.get(tool["name"])
                    if live and live.get("description"):
                        tool["description"] = live["description"]
                for resource in out["resources"]:
                    live = live_resources.get(resource["uri"])
                    if live and live.get("description"):
                        resource["description"] = live["description"]
                for prompt in out["prompts"]:
                    live = live_prompts.get(prompt["name"])
                    if live and live.get("description"):
                        prompt["description"] = live["description"]
        except Exception:
            pass
    return out


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
    try:
        resolved = _resolve_resource_uri(body.uri, body.params)
    except HTTPException:
        raise

    from mcp_reference_service import is_reference_resource_uri, read_reference_resource_content

    if is_reference_resource_uri(resolved):
        domain_slug = str((body.params or {}).get("domain", "")).strip() or None
        domain_id = body.domain_id
        if not domain_id and domain_slug:
            row = get_domain(slug=domain_slug)
            domain_id = row["id"] if row else None
        try:
            content = read_reference_resource_content(
                resolved,
                domain_id=domain_id,
                domain_slug=domain_slug,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    else:
        status = get_server_status(registry)
        if not status["reachable"]:
            raise HTTPException(503, "MCP server is not reachable — start it to preview resources.")
        try:
            content = read_resource_preview(status["url"], resolved)
        except Exception as exc:
            raise HTTPException(502, _mcp_client_error_message(exc)) from exc

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


@router.get("/prompts/{name}/meta")
def mcp_prompt_meta(name: str, domain_id: str | None = Query(default=None)):
    if is_local_prompt_name(name):
        if not domain_id:
            raise HTTPException(400, "domain_id is required for local prompts")
        slug = local_prompt_slug(name)
        local = get_domain_prompt(domain_id, slug=slug)
        if not local:
            raise HTTPException(404, f"Unknown local prompt: {slug}")
        template = local.get("template") or ""
        params = prompt_template_parameters(template)
        auto_filled = {
            "domain",
            "domain_name",
            "schema",
            "calendar",
            "glossary",
            "sql_notes",
            "tool_context",
            "citation_rules",
        }
        domain_filled = sorted(p for p in params if p in auto_filled)
        return {
            "name": name,
            "description": local.get("description") or "",
            "parameters": params,
            "domain_context": bool(domain_filled),
            "domain_filled_parameters": domain_filled,
            "enabled": bool(local.get("enabled", True)),
            "prompt_kind": "local",
            "local_slug": slug,
            "local_prompt_id": local["id"],
        }
    if name not in REGISTRY_DEFAULTS["prompts"]:
        raise HTTPException(404, f"Unknown prompt: {name}")
    registry = load_registry()
    meta = get_prompt_meta(name, registry)
    domain_filled = sorted(_DOMAIN_CONTEXT_PROMPT_ARGS.get(name, frozenset()))
    return {
        "name": name,
        "description": meta["description"],
        "parameters": _prompt_arguments_from_live(registry, name),
        "domain_context": bool(domain_filled),
        "domain_filled_parameters": domain_filled,
        "enabled": meta["enabled"],
        "prompt_kind": "global",
    }


@router.post("/prompts/{name}/preview")
def preview_prompt(name: str, body: McpPromptPreviewBody | None = None):
    domain_id = body.domain_id if body else None
    user_args = (body.arguments if body else None) or {}

    if is_local_prompt_name(name):
        if not domain_id:
            raise HTTPException(400, "domain_id is required for local prompts")
        slug = local_prompt_slug(name)
        if not get_domain_prompt(domain_id, slug=slug):
            raise HTTPException(404, f"Unknown local prompt: {slug}")
        domain = get_domain(domain_id=domain_id) or {}
        try:
            preview = render_domain_local_prompt(
                domain_id,
                slug,
                domain_slug=domain.get("slug"),
                user_args=user_args,
            )
        except Exception as exc:
            raise HTTPException(502, str(exc)) from exc
        from domain_prompt_service import build_local_prompt_context

        args = build_local_prompt_context(domain_id, domain_slug=domain.get("slug"), user_args=user_args)
        return {"preview": preview, "arguments": args, "prompt_kind": "local"}

    if name not in REGISTRY_DEFAULTS["prompts"]:
        raise HTTPException(404, f"Unknown prompt: {name}")
    registry = load_registry()
    status = get_server_status(registry)
    if not status["reachable"]:
        raise HTTPException(503, "MCP server is not reachable — start it to preview live prompts.")
    args = _build_prompt_preview_arguments(name, domain_id, user_args)
    try:
        preview = get_prompt_preview(status["url"], name, args)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"preview": preview, "arguments": args, "prompt_kind": "global"}


@router.get("/binding-catalog")
def binding_catalog():
    """All registered MCP servers and discoverable capabilities for domain binding UI."""
    registry = load_registry()
    servers = list_mcp_servers(enabled_only=False)
    catalog = []
    for server in servers:
        caps = _live_capabilities_for_server(server, registry)
        catalog.append({"server": server, **caps})
    return {"servers": catalog}


@router.get("/servers")
def mcp_servers_list():
    servers = list_mcp_servers(enabled_only=False)
    dismissed = list_dismissed_optional_mcp_servers()
    return {
        "servers": [enrich_server_runtime(server) for server in servers],
        "dismissed_optional": dismissed,
    }


@router.post("/servers/restore/{slug}")
def mcp_server_restore(slug: str):
    server = restore_optional_mcp_server(slug)
    if not server:
        raise HTTPException(404, "Unknown or unavailable optional MCP server")
    return {"ok": True, "server": enrich_server_runtime(server)}


@router.post("/servers/{server_id}/start")
def mcp_server_start(server_id: str):
    server = get_mcp_server(server_id=server_id)
    if not server:
        raise HTTPException(404, "MCP server not found")
    if server.get("is_builtin"):
        registry = load_registry()
        ok, message = start_server(registry)
        return {"ok": ok, "message": message, "server": enrich_server_runtime(server)}
    ok, message = start_integration(server["slug"], url=server["url"])
    return {
        "ok": ok,
        "message": message,
        "server": enrich_server_runtime(get_mcp_server(server_id=server_id) or server),
    }


@router.post("/servers/{server_id}/stop")
def mcp_server_stop(server_id: str):
    server = get_mcp_server(server_id=server_id)
    if not server:
        raise HTTPException(404, "MCP server not found")
    if server.get("is_builtin"):
        registry = load_registry()
        ok, message = stop_server(registry)
        return {"ok": ok, "message": message, "server": enrich_server_runtime(server)}
    ok, message = stop_integration(server["slug"], url=server["url"])
    return {
        "ok": ok,
        "message": message,
        "server": enrich_server_runtime(get_mcp_server(server_id=server_id) or server),
    }


@router.post("/servers")
def mcp_server_create(body: McpServerCreate):
    if body.server_kind not in ("public", "enterprise"):
        raise HTTPException(400, "server_kind must be public or enterprise")
    server = create_mcp_server(
        body.name.strip(),
        body.url.strip(),
        description=body.description.strip(),
        server_kind=body.server_kind,
        transport=body.transport.strip() or "streamable-http",
    )
    return {"ok": True, "server": server}


@router.put("/servers/{server_id}")
def mcp_server_update(server_id: str, body: McpServerUpdate):
    server = get_mcp_server(server_id=server_id)
    if not server:
        raise HTTPException(404, "MCP server not found")
    if server.get("is_builtin"):
        if body.url is None:
            raise HTTPException(400, "Built-in MCP server: only url can be updated")
        updated = update_mcp_server(server_id, url=body.url.strip())
        return {"ok": True, "server": enrich_server_runtime(updated or server)}
    if body.server_kind is not None and body.server_kind not in ("public", "enterprise"):
        raise HTTPException(400, "server_kind must be public or enterprise")
    updated = update_mcp_server(
        server_id,
        name=body.name.strip() if body.name is not None else None,
        url=body.url.strip() if body.url is not None else None,
        description=body.description.strip() if body.description is not None else None,
        server_kind=body.server_kind,
        transport=body.transport.strip() if body.transport is not None else None,
        enabled=body.enabled,
    )
    return {"ok": True, "server": enrich_server_runtime(updated or server)}


@router.delete("/servers/{server_id}")
def mcp_server_delete(server_id: str):
    server = get_mcp_server(server_id=server_id)
    if not server:
        raise HTTPException(404, "MCP server not found")
    if server.get("is_builtin"):
        raise HTTPException(400, "Built-in MCP server cannot be deleted")
    if not delete_mcp_server(server_id):
        raise HTTPException(404, "MCP server not found")
    return {"ok": True}


@router.get("/servers/{server_id}/capabilities")
def mcp_server_capabilities(server_id: str):
    server = get_mcp_server(server_id=server_id)
    if not server:
        raise HTTPException(404, "MCP server not found")
    return _live_capabilities_for_server(server)


@router.get("/bindings")
def mcp_bindings(domain_id: str):
    if not any(d["id"] == domain_id for d in list_domains(enabled_only=False)):
        raise HTTPException(404, "Domain not found")
    bindings = list_mcp_bindings(domain_id)
    return {"domain_id": domain_id, "bindings": _group_bindings(bindings, domain_id=domain_id)}


@router.post("/bindings")
def add_binding(body: McpBindingAdd):
    if body.capability_type not in ("tool", "resource", "prompt"):
        raise HTTPException(400, "capability_type must be tool, resource, or prompt")
    if not get_mcp_server(server_id=body.mcp_server_id):
        raise HTTPException(404, "MCP server not found")
    if not any(d["id"] == body.domain_id for d in list_domains(enabled_only=False)):
        raise HTTPException(404, "Domain not found")
    binding = add_mcp_binding(
        body.domain_id,
        body.mcp_server_id,
        body.capability_type,
        body.capability_name.strip(),
    )
    return {"ok": True, "binding": binding}


@router.delete("/bindings/{binding_id}")
def delete_binding(binding_id: str):
    if not remove_mcp_binding(binding_id):
        raise HTTPException(404, "Binding not found")
    return {"ok": True}


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
        mcp_server_id=body.mcp_server_id,
    )
    return {"ok": True}
