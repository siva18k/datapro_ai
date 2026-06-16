"""In-memory cache for domain routing metadata (refreshed on catalog writes)."""

from __future__ import annotations

from catalog_db import get_rag_profile, list_column_metadata, list_domains, list_sources, list_table_metadata

_routing_context_cache: list[dict] | None = None


def clear_routing_cache() -> None:
    global _routing_context_cache
    _routing_context_cache = None
    try:
        from query_fuzzy import clear_vocabulary_cache

        clear_vocabulary_cache()
    except Exception:
        pass


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
            routing_parts = [
                source.get("name") or "",
                source.get("description") or "",
                source.get("slug") or "",
            ]
            for table in list_table_metadata(source["id"]):
                if not table.get("enabled", True):
                    continue
                if (table.get("table_role") or "fact") == "excluded":
                    continue
                routing_parts.append(table.get("table_name") or "")
                if table.get("definition"):
                    routing_parts.append(table["definition"])
                for col in list_column_metadata(table["id"]):
                    routing_parts.append(col.get("column_name") or "")
                    routing_parts.extend(col.get("labels") or [])
                    if col.get("description"):
                        routing_parts.append(col["description"])
            profile = get_rag_profile(source["id"])
            if profile:
                if profile.get("instructions"):
                    routing_parts.append(profile["instructions"])
                if profile.get("metadata_text"):
                    routing_parts.append(profile["metadata_text"])
            routing_text = " ".join(p for p in routing_parts if p)

            sources_out.append(
                {
                    "id": source["id"],
                    "name": source["name"],
                    "description": source["description"],
                    "source_type": source["source_type"],
                    "connector": source.get("connector"),
                    "table_names": table_names,
                    "routing_text": routing_text,
                }
            )
        context.append({**domain, "sources": sources_out})

    _routing_context_cache = context
    return context
