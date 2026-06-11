"""In-memory cache for domain routing metadata (refreshed on catalog writes)."""

from __future__ import annotations

from catalog_db import list_domains, list_sources, list_table_metadata

_routing_context_cache: list[dict] | None = None


def clear_routing_cache() -> None:
    global _routing_context_cache
    _routing_context_cache = None


def get_cached_routing_context() -> list[dict]:
    """Domains + sources + table names for fast keyword routing."""
    global _routing_context_cache
    if _routing_context_cache is not None:
        return _routing_context_cache

    context: list[dict] = []
    for domain in list_domains():
        sources_out: list[dict] = []
        for source in list_sources(domain_id=domain["id"]):
            table_names: list[str] = []
            if source.get("source_type") == "structured":
                table_names = [
                    t["table_name"]
                    for t in list_table_metadata(source["id"])
                    if t.get("enabled", True)
                ]
            sources_out.append(
                {
                    "id": source["id"],
                    "name": source["name"],
                    "description": source["description"],
                    "source_type": source["source_type"],
                    "connector": source.get("connector"),
                    "table_names": table_names,
                }
            )
        context.append({**domain, "sources": sources_out})

    _routing_context_cache = context
    return context
