"""Shared MCP tool payloads, parameter docs, and source resolution."""

from __future__ import annotations

import uuid
from typing import Any

from catalog_db import get_source
from catalog_service import list_dataset_assets, resolve_domain, sync_dataset_source

# Planner / agent hints — keep in sync with mcp_registry tool descriptions.
MCP_TOOL_GUIDE = """
MCP tool naming (DATA Pro):
- **list_domains** — business domains (HR, Finance, …). No arguments.
- **list_domain_sources** — catalog *datasets* under a domain. Arg: `domain` (slug, name, or UUID).
- **list_sources** — ingested *document files* in the vector KB (chunk counts). No domain arg. NOT catalog datasets.
- **search_documents** — semantic chunk search. Args: `query`, optional `top_k`, optional `domain`.
- **get_rag_profile** — RAG settings for a dataset. Args: `source_id` (UUID or dataset slug), optional `domain` when using slug.
- **sync_dataset** — fetch remote content (API, web link, SharePoint) into the dataset cache. Args: `source_id`, optional `domain`, optional `full` refresh.
- **resolve_time_period** — calendar/fiscal periods + SQL date filters. Arg: `requirement` (natural language).
""".strip()

DOMAIN_ARG = (
    "Business domain slug (e.g. finance), display name, or UUID. "
    "Use list_domains when the domain is unknown."
)
SOURCE_ID_ARG = (
    "Dataset/source UUID, or dataset slug when `domain` is also provided."
)
SOURCE_DOMAIN_ARG = (
    "Domain slug, name, or UUID — required when source_id is a dataset slug, not a UUID."
)
SEARCH_QUERY_ARG = "Natural-language search query over ingested document chunks."
SEARCH_TOP_K_ARG = "Maximum number of chunks to return (1–20)."
SEARCH_DOMAIN_ARG = (
    "Optional domain slug, name, or UUID to scope vector search. Omit to search all domains."
)
TIME_REQUIREMENT_ARG = (
    "Natural-language time requirement, e.g. 'Q1 2024', 'last year by month', 'FY2025 YTD'."
)


def serialize_domain(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "description": row.get("description"),
    }


def serialize_domain_source(row: dict[str, Any]) -> dict[str, Any]:
    cfg = row.get("config") or {}
    payload = {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "description": row.get("description"),
        "source_type": row.get("source_type"),
        "connector": row.get("connector"),
        "domain_id": row.get("domain_id"),
        "domain_slug": row.get("domain_slug"),
        "enabled": row.get("enabled", True),
        "last_sync_at": cfg.get("last_sync_at"),
    }
    try:
        payload["asset_count"] = len(list_dataset_assets(row))
    except Exception:
        payload["asset_count"] = None
    return payload


def resolve_source_identifier(source_id: str, domain: str | None = None) -> dict[str, Any] | None:
    """Resolve a dataset by UUID, or by slug within a domain."""
    identifier = (source_id or "").strip()
    if not identifier:
        return None
    try:
        uuid.UUID(identifier)
        row = get_source(source_id=identifier)
        if row:
            return row
    except ValueError:
        pass
    domain_row = resolve_domain(domain) if domain else None
    if domain_row:
        return get_source(slug=identifier.lower(), domain_id=domain_row["id"])
    return None


def domain_sources_payload(domain_id: str) -> list[dict[str, Any]]:
    from catalog_db import list_sources as catalog_list_sources

    return [serialize_domain_source(s) for s in catalog_list_sources(domain_id=domain_id)]
