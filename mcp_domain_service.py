"""Resolve per-domain MCP servers and run bound tools/prompts at ask time."""

from __future__ import annotations

from typing import Any

from catalog_db import ensure_builtin_mcp_server, get_domain, list_domain_mcp_capabilities, list_mcp_servers
from mcp_client import (
    check_mcp_server,
    get_default_mcp_url,
    read_resource_preview,
    search_documents,
)
from mcp_reference_service import (
    REFERENCE_RESOURCE_URIS,
    expand_domain_uri,
    is_reference_resource_uri,
    read_reference_resource_content,
    reference_uris_for_execution,
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


def _binding_covers_uri(binding_uri: str, target_uri: str, domain_slug: str | None) -> bool:
    if binding_uri == target_uri:
        return True
    if domain_slug and "{domain}" in binding_uri:
        return binding_uri.replace("{domain}", domain_slug) == target_uri
    return False


def _is_reference_bound(bound_uris: set[str], target_uri: str, domain_slug: str | None) -> bool:
    return any(_binding_covers_uri(uri, target_uri, domain_slug) for uri in bound_uris)


def load_domain_reference_resources(
    domain_id: str | None,
    *,
    domain_slug: str | None,
    execution_kind: str,
) -> list[dict[str, Any]]:
    """Load application-controlled reference resources (schema, calendar, glossary, …)."""
    if not domain_id:
        return []

    bound = {
        c["capability_name"]
        for c in domain_mcp_capabilities(domain_id, "resource")
        if c.get("capability_name")
    }
    if not bound:
        return []

    builtin_url = _builtin_server_url()
    out: list[dict[str, Any]] = []

    for key in reference_uris_for_execution(execution_kind):
        if key == "citation_rules":
            uri = REFERENCE_RESOURCE_URIS["citation_rules"]
        else:
            uri = expand_domain_uri(REFERENCE_RESOURCE_URIS[key], domain_slug)

        if not _is_reference_bound(bound, uri, domain_slug):
            continue

        try:
            content = read_reference_resource_content(
                uri, domain_id=domain_id, domain_slug=domain_slug
            )
        except Exception as exc:
            content = f"[reference error: {exc}]"

        if content:
            out.append(
                {
                    "uri": uri,
                    "kind": "reference",
                    "reference_key": key,
                    "server": "datapro",
                    "mcp_url": builtin_url,
                    "content": content[:12000],
                }
            )
    return out


def read_optional_resources_for_domain(
    domain_id: str | None,
    *,
    domain_slug: str | None = None,
) -> list[dict[str, Any]]:
    """Load dynamic inventory resources when planner requests use_resources."""
    if not domain_id:
        return []
    out: list[dict] = []
    for resource in domain_mcp_capabilities(domain_id, "resource"):
        uri = resource.get("capability_name")
        if not uri:
            continue
        resolved_uri = expand_domain_uri(uri, domain_slug)
        if is_reference_resource_uri(resolved_uri):
            continue
        url = resource["server_url"]
        if not url or not check_mcp_server(url):
            continue
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
                    "kind": "optional",
                    "server": resource.get("server_slug"),
                    "content": content[:4000],
                }
            )
    return out


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


def ensure_mcp_catalog_ready() -> None:
    ensure_builtin_mcp_server()
