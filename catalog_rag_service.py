"""Embed catalog metadata (and lookup table rows) for structured datasets."""

from __future__ import annotations

from typing import Any

from catalog_db import (
    get_rag_profile,
    list_column_metadata,
    list_table_metadata,
    update_rag_profile,
)
from catalog_service import load_dataset_definition
from db import connect, get_db_config, upsert_chunks
from ingest_service import chunk_text
from structured_db import postgres_config_from_source
from structured_orchestrator import execute_readonly_sql

CATALOG_SOURCE_PREFIX = "catalog_meta/"
LOOKUP_SOURCE_PREFIX = "lookup_data/"
LOOKUP_ROW_LIMIT = 500
LOOKUP_ROWS_PER_CHUNK = 25


def _chunk_id_prefix(domain_slug: str, source_slug: str) -> str:
    return f"{domain_slug}_{source_slug}"


def _scoped_catalog_source_file(domain_slug: str, source_slug: str, name: str) -> str:
    return f"{CATALOG_SOURCE_PREFIX}{domain_slug}/{source_slug}/{name}"


def _scoped_lookup_source_file(domain_slug: str, source_slug: str, table_name: str) -> str:
    return f"{LOOKUP_SOURCE_PREFIX}{domain_slug}/{source_slug}/{table_name}"


def delete_structured_rag_chunks(source: dict) -> int:
    """Remove catalog metadata and lookup embeddings for a dataset."""
    schema = get_db_config()["schema"]
    domain_slug = source.get("domain_slug", "domain")
    source_slug = source.get("slug", "ds")
    prefix = _chunk_id_prefix(domain_slug, source_slug)
    scoped_catalog = f"{CATALOG_SOURCE_PREFIX}{domain_slug}/{source_slug}/%"
    scoped_lookup = f"{LOOKUP_SOURCE_PREFIX}{domain_slug}/{source_slug}/%"
    conn, _ = connect()
    try:
        rows = conn.run(
            f"""
            DELETE FROM {schema}.knowledge_chunks
            WHERE source_id = :source_id::uuid
               OR id LIKE :id_prefix
               OR source_file LIKE :scoped_catalog
               OR source_file LIKE :scoped_lookup
               OR (
                 id LIKE :id_prefix
                 AND (
                   source_file LIKE 'catalog_meta/%'
                   OR source_file LIKE 'lookup_data/%'
                 )
               )
            RETURNING id
            """,
            source_id=source["id"],
            id_prefix=f"{prefix}_%",
            scoped_catalog=scoped_catalog,
            scoped_lookup=scoped_lookup,
        )
        return len(rows)
    finally:
        conn.close()


def build_catalog_metadata_text(source: dict) -> list[dict[str, str]]:
    """One text block per cataloged table (+ dataset overview)."""
    blocks: list[dict[str, str]] = []
    definition_md = load_dataset_definition(source)
    overview = [
        f"[Catalog — {source.get('domain_name', '')} / {source.get('name', '')}]",
        f"Dataset: {source.get('name', '')}",
        f"Connector: {source.get('connector', '')}",
        f"Type: structured (metadata for routing and SQL grounding; not full table data)",
        "",
        "## Dataset definition",
        definition_md or "(none)",
    ]
    blocks.append({"key": "_overview", "text": "\n".join(overview)})

    for table in list_table_metadata(source["id"]):
        if not table.get("enabled", True):
            continue
        role = table.get("table_role") or "fact"
        if role == "excluded":
            continue

        lines = [
            f"[Catalog table — {table['table_schema']}.{table['table_name']}]",
            f"Dataset: {source.get('name', '')}",
            f"Domain: {source.get('domain_name', '')}",
            f"Role: {role}",
        ]
        if table.get("definition"):
            lines.extend(["", "## Table definition", table["definition"]])
        lines.extend(["", "## Columns"])
        for col in list_column_metadata(table["id"]):
            labels = ", ".join(col.get("labels") or []) or "—"
            desc = col.get("description") or ""
            line = f"- `{col['column_name']}` ({col.get('data_type', '?')}) labels: [{labels}]"
            if desc:
                line += f" — {desc}"
            lines.append(line)
        if role == "lookup":
            lines.append("")
            lines.append(
                "This is a lookup/reference table; row values are also embedded for direct retrieval."
            )
        blocks.append({"key": table["table_name"], "text": "\n".join(lines)})

    return blocks


def _is_lookup_table(table: dict) -> bool:
    return (
        table.get("enabled", True)
        and (table.get("table_role") or "fact") == "lookup"
    )


def _lookup_row_chunks(source: dict, table: dict, profile: dict | None) -> list[dict[str, Any]]:
    """Embed lookup table rows as searchable text (cataloged columns only)."""
    if not _is_lookup_table(table):
        return []

    schema_name = table["table_schema"]
    table_name = table["table_name"]
    columns_meta = list_column_metadata(table["id"])
    if not columns_meta:
        return []
    col_names = [col["column_name"] for col in columns_meta]
    quoted_cols = ", ".join(f'"{name}"' for name in col_names)
    sql = (
        f'SELECT {quoted_cols} FROM "{schema_name}"."{table_name}" '
        f"LIMIT {LOOKUP_ROW_LIMIT}"
    )
    try:
        columns, rows = execute_readonly_sql(source["id"], sql, max_rows=LOOKUP_ROW_LIMIT)
    except Exception:
        return []

    if not rows:
        return []

    profile = profile or {}
    chunk_size = profile.get("chunk_size") or 800
    chunk_overlap = profile.get("chunk_overlap") or 80
    domain_slug = source.get("domain_slug", "domain")
    source_slug = source.get("slug", "ds")
    prefix = _chunk_id_prefix(domain_slug, source_slug)
    items: list[dict[str, Any]] = []

    for batch_start in range(0, len(rows), LOOKUP_ROWS_PER_CHUNK):
        batch = rows[batch_start : batch_start + LOOKUP_ROWS_PER_CHUNK]
        row_lines = [
            f"[Lookup data — {schema_name}.{table_name}]",
            f"Dataset: {source.get('name', '')}",
            "",
        ]
        for row in batch:
            pairs = [f"{columns[i]}={row[i]}" for i in range(min(len(columns), len(row)))]
            row_lines.append(" | ".join(pairs))
        text = "\n".join(row_lines)
        for i, piece in enumerate(chunk_text(text, chunk_size, chunk_overlap)):
            chunk_idx = batch_start // LOOKUP_ROWS_PER_CHUNK
            items.append(
                {
                    "id": f"{prefix}_lk_{table_name}_{chunk_idx}_{i}",
                    "source_file": _scoped_lookup_source_file(
                        domain_slug, source_slug, table_name
                    ),
                    "chunk_id": f"rows_{chunk_idx:03d}_{i:02d}",
                    "content": piece,
                    "domain_id": source["domain_id"],
                    "source_id": source["id"],
                    "rag_profile_id": profile.get("id") if profile else None,
                }
            )
    return items


def build_catalog_rag_items(source: dict, profile: dict | None) -> list[dict[str, Any]]:
    """Chunks for catalog metadata, optional lookup row data, and profile instructions."""
    profile = profile or get_rag_profile(source["id"]) or {}
    chunk_size = profile.get("chunk_size") or 400
    chunk_overlap = profile.get("chunk_overlap") or 60
    domain_slug = source.get("domain_slug", "domain")
    source_slug = source.get("slug", "ds")
    prefix = _chunk_id_prefix(domain_slug, source_slug)
    rag_profile_id = profile.get("id")
    items: list[dict[str, Any]] = []

    for block in build_catalog_metadata_text(source):
        key = block["key"]
        source_file = _scoped_catalog_source_file(
            domain_slug,
            source_slug,
            "overview" if key == "_overview" else key,
        )
        for i, piece in enumerate(chunk_text(block["text"], chunk_size, chunk_overlap)):
            items.append(
                {
                    "id": f"{prefix}_cat_{key}_{i}",
                    "source_file": source_file,
                    "chunk_id": f"meta_{i:02d}",
                    "content": piece,
                    "domain_id": source["domain_id"],
                    "source_id": source["id"],
                    "rag_profile_id": rag_profile_id,
                }
            )

    for table in list_table_metadata(source["id"]):
        items.extend(_lookup_row_chunks(source, table, profile))

    instructions = (profile.get("instructions") or "").strip()
    if instructions:
        for i, piece in enumerate(chunk_text(instructions, chunk_size, chunk_overlap)):
            items.append(
                {
                    "id": f"{prefix}_instructions_{i}",
                    "source_file": _scoped_catalog_source_file(
                        domain_slug, source_slug, "instructions"
                    ),
                    "chunk_id": f"instr_{i:02d}",
                    "content": piece,
                    "domain_id": source["domain_id"],
                    "source_id": source["id"],
                    "rag_profile_id": rag_profile_id,
                }
            )

    return items


def index_structured_catalog(source: dict, embedder, *, replace_existing: bool = True) -> dict:
    """
    Embed catalog metadata (and lookup rows) into knowledge_chunks.
    Structured datasets should use this instead of document file ingest.
    """
    if source.get("source_type") != "structured":
        raise ValueError("Catalog indexing applies to structured datasets only")

    profile = get_rag_profile(source["id"])
    removed = delete_structured_rag_chunks(source) if replace_existing else 0
    items = build_catalog_rag_items(source, profile)
    written = upsert_chunks(items, embedder) if items else 0
    if profile:
        update_rag_profile(source["id"], touch_ingested=True)

    meta_tables = sum(
        1
        for t in list_table_metadata(source["id"])
        if t.get("enabled", True) and (t.get("table_role") or "fact") != "excluded"
    )
    lookup_tables = sum(1 for t in list_table_metadata(source["id"]) if _is_lookup_table(t))

    return {
        "removed_chunks": removed,
        "catalog_chunks": written,
        "metadata_tables": meta_tables,
        "lookup_tables": lookup_tables,
        "source_file": CATALOG_SOURCE_PREFIX,
    }
