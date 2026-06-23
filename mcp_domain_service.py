"""Resolve per-domain MCP servers and run bound tools/prompts at ask time."""

from __future__ import annotations

from typing import Any

from catalog_db import ensure_builtin_mcp_server, get_domain, list_domain_mcp_capabilities, list_mcp_servers
from mcp_client import (
    call_tool,
    check_mcp_server,
    get_default_mcp_url,
    get_prompt_preview,
    read_resource_preview,
    search_documents,
)


def _builtin_server_url() -> str:
    servers = list_mcp_servers(enabled_only=False)
    for server in servers:
        if server.get("is_builtin"):
            return server["url"]
    return get_default_mcp_url()


def domain_mcp_capabilities(domain_id: str | None, capability_type: str) -> list[dict]:
    if not domain_id:
        return []
    caps = list_domain_mcp_capabilities(domain_id, capability_type, enabled_only=True)
    return [c for c in caps if c.get("server_enabled", True)]


def retrieve_chunks_for_domain(
    question: str,
    *,
    domain_id: str | None,
    domain_slug: str | None,
    top_k: int,
) -> tuple[list[dict], dict[str, Any] | None]:
    """
    Search using domain-bound MCP search tools (search_documents).
    Returns (chunks, trace_meta) where trace_meta describes the server/tool used.
    """
    tools = domain_mcp_capabilities(domain_id, "tool") if domain_id else []
    search_tools = [t for t in tools if t["capability_name"] == "search_documents"]

    if not search_tools:
        url = _builtin_server_url()
        if check_mcp_server(url):
            domain_arg = domain_slug if domain_slug else None
            chunks = search_documents(url, question, top_k=top_k, domain=domain_arg)
            if chunks:
                return chunks, {
                    "mcp_url": url,
                    "mcp_tool": "search_documents",
                    "mcp_server": "datapro",
                    "fallback": True,
                }
        return [], None

    for tool in search_tools:
        url = tool["server_url"]
        if not url or not check_mcp_server(url):
            continue
        domain_arg = domain_slug if domain_slug else None
        try:
            chunks = search_documents(url, question, top_k=top_k, domain=domain_arg)
        except Exception:
            continue
        if chunks:
            return chunks, {
                "mcp_url": url,
                "mcp_tool": "search_documents",
                "mcp_server": tool.get("server_slug") or tool.get("server_name"),
                "mcp_server_id": tool.get("mcp_server_id"),
            }

    return [], None


def retrieve_chunks_for_scope(
    question: str,
    *,
    domain_id: str | None,
    domain_ids: list[str] | None,
    domain_slug: str | None,
    top_k: int,
) -> tuple[list[dict], dict[str, Any] | None]:
    """Search with domain-bound MCP tools; supports multi-domain scope."""
    ids = domain_ids or ([domain_id] if domain_id else [])
    if len(ids) <= 1:
        return retrieve_chunks_for_domain(
            question,
            domain_id=ids[0] if ids else domain_id,
            domain_slug=domain_slug,
            top_k=top_k,
        )

    merged: list[dict] = []
    trace: dict[str, Any] | None = None
    per_domain = max(1, top_k // len(ids))
    for did in ids:
        domain = get_domain(domain_id=did)
        slug = domain.get("slug") if domain else None
        chunks, meta = retrieve_chunks_for_domain(
            question, domain_id=did, domain_slug=slug, top_k=per_domain
        )
        if chunks:
            merged.extend(chunks)
            trace = trace or meta
    merged.sort(key=lambda c: float(c.get("distance", float("inf"))))
    return merged[:top_k], trace


def build_prompt_via_domain_mcp(
    question: str,
    *,
    domain_id: str | None,
    domain_slug: str | None,
    top_k: int = 3,
) -> tuple[str | None, dict[str, Any] | None]:
    """
    If domain binds a grounded-answer prompt, render it from the bound MCP server.
    Returns (prompt_text, trace_meta) or (None, None) to fall back to local RAG prompt.
    """
    if not domain_id:
        return None, None

    preferred = ("domain_grounded_answer", "grounded_answer")
    prompts = domain_mcp_capabilities(domain_id, "prompt")
    ordered = sorted(
        prompts,
        key=lambda p: preferred.index(p["capability_name"])
        if p["capability_name"] in preferred
        else len(preferred),
    )

    for prompt in ordered:
        if prompt["capability_name"] not in preferred:
            continue
        url = prompt["server_url"]
        if not url or not check_mcp_server(url):
            continue
        args: dict[str, str] = {"question": question, "top_k": str(top_k)}
        if domain_slug and prompt["capability_name"] == "domain_grounded_answer":
            args["domain"] = domain_slug
        try:
            text = get_prompt_preview(url, prompt["capability_name"], args)
        except Exception:
            continue
        if text and text.strip():
            return text, {
                "mcp_url": url,
                "mcp_prompt": prompt["capability_name"],
                "mcp_server": prompt.get("server_slug") or prompt.get("server_name"),
                "mcp_server_id": prompt.get("mcp_server_id"),
            }

    return None, None


def _expand_resource_uri(uri: str, domain_slug: str | None) -> str:
    if domain_slug and "{domain}" in uri:
        return uri.replace("{domain}", domain_slug)
    return uri


def read_bound_resources_for_domain(
    domain_id: str | None,
    *,
    domain_slug: str | None = None,
) -> list[dict[str, Any]]:
    """Optional context from bound MCP resources (best-effort)."""
    if not domain_id:
        return []
    out: list[dict] = []
    for resource in domain_mcp_capabilities(domain_id, "resource"):
        url = resource["server_url"]
        uri = resource.get("capability_name")
        if not url or not uri or not check_mcp_server(url):
            continue
        resolved_uri = _expand_resource_uri(uri, domain_slug)
        try:
            content = read_resource_preview(url, resolved_uri)
        except Exception:
            if resolved_uri != uri:
                try:
                    content = read_resource_preview(url, uri)
                except Exception:
                    continue
            else:
                continue
        if content:
            out.append(
                {
                    "uri": resolved_uri,
                    "server": resource.get("server_slug"),
                    "content": content[:4000],
                }
            )
    return out


def ensure_mcp_catalog_ready() -> None:
    ensure_builtin_mcp_server()
