"""Embed catalog metadata (and lookup table rows) for structured datasets."""

from __future__ import annotations

from typing import Any

from catalog_db import (
    get_rag_profile,
    get_source,
    list_column_metadata,
    list_source_file_rag,
    list_table_metadata,
    update_rag_profile,
)
from catalog_definition import load_definition_for_prompt
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


def _table_chunk_settings(table: dict, profile: dict | None) -> tuple[int, int]:
    profile = profile or {}
    chunk_size = table.get("chunk_size") or profile.get("chunk_size") or 400
    chunk_overlap = table.get("chunk_overlap") or profile.get("chunk_overlap") or 60
    return int(chunk_size), int(chunk_overlap)


def should_rag_table(table: dict) -> bool:
    if not table.get("enabled", True):
        return False
    if (table.get("table_role") or "fact") == "excluded":
        return False
    return bool(table.get("rag_enabled", True))


def _chunk_source_file(chunk: dict[str, Any]) -> str:
    return str(chunk.get("source") or chunk.get("source_file") or "")


def filter_chunks_to_rag_selection(
    chunks: list[dict[str, Any]],
    *,
    source_id: str | None = None,
    table_names: list[str] | None = None,
    file_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Keep only chunks from catalog tables/files selected for RAG (Ask / Analytics retrieval)."""
    if not chunks:
        return []

    allowed_tables = {t.lower() for t in table_names} if table_names else None
    allowed_files = set(file_names) if file_names else None

    grouped: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        sid = chunk.get("source_id") or source_id
        if sid:
            grouped.setdefault(str(sid), []).append(chunk)
        else:
            grouped.setdefault("", []).append(chunk)

    filtered: list[dict[str, Any]] = []
    for sid, group in grouped.items():
        if not sid:
            filtered.extend(group)
            continue
        source = get_source(source_id=sid)
        if not source:
            filtered.extend(group)
            continue

        if source.get("source_type") == "structured":
            enabled_tables = {
                t["table_name"]
                for t in list_table_metadata(sid)
                if should_rag_table(t)
            }
            include_shared = bool(enabled_tables)
            domain_slug = source.get("domain_slug") or "domain"
            source_slug = source.get("slug") or "ds"
            catalog_prefix = f"{CATALOG_SOURCE_PREFIX}{domain_slug}/{source_slug}/"
            lookup_prefix = f"{LOOKUP_SOURCE_PREFIX}{domain_slug}/{source_slug}/"
            for chunk in group:
                sf = _chunk_source_file(chunk)
                if sf.startswith(catalog_prefix):
                    name = sf[len(catalog_prefix) :]
                    if allowed_tables is not None and name.lower() not in allowed_tables:
                        continue
                    if name in enabled_tables or (include_shared and name in ("overview", "instructions")):
                        filtered.append(chunk)
                elif sf.startswith(lookup_prefix):
                    name = sf[len(lookup_prefix) :]
                    if allowed_tables is not None and name.lower() not in allowed_tables:
                        continue
                    if name in enabled_tables:
                        filtered.append(chunk)
                else:
                    filtered.append(chunk)
        else:
            file_settings = {
                row["file_name"]: bool(row.get("rag_enabled", True))
                for row in list_source_file_rag(sid)
            }
            slug = source.get("slug") or "dataset"
            for chunk in group:
                sf = _chunk_source_file(chunk)
                if sf.endswith("_instructions") or sf == f"{slug}_instructions":
                    filtered.append(chunk)
                    continue
                if allowed_files is not None and sf not in allowed_files:
                    continue
                if file_settings and sf in file_settings:
                    if file_settings[sf]:
                        filtered.append(chunk)
                else:
                    filtered.append(chunk)

    return filtered


def delete_structured_rag_chunks(source: dict) -> int:
    """Remove all catalog metadata and lookup embeddings for a dataset."""
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


def delete_table_rag_chunks(source: dict, table: dict) -> int:
    """Remove embeddings for one catalog table (metadata + lookup rows)."""
    domain_slug = source.get("domain_slug", "domain")
    source_slug = source.get("slug", "ds")
    table_name = table["table_name"]
    prefix = _chunk_id_prefix(domain_slug, source_slug)
    catalog_file = _scoped_catalog_source_file(domain_slug, source_slug, table_name)
    lookup_file = _scoped_lookup_source_file(domain_slug, source_slug, table_name)
    schema = get_db_config()["schema"]
    conn, _ = connect()
    try:
        rows = conn.run(
            f"""
            DELETE FROM {schema}.knowledge_chunks
            WHERE source_id = :source_id::uuid
              AND (
                source_file = :catalog_file
                OR source_file = :lookup_file
                OR id LIKE :table_id_prefix
              )
            RETURNING id
            """,
            source_id=source["id"],
            catalog_file=catalog_file,
            lookup_file=lookup_file,
            table_id_prefix=f"{prefix}_cat_{table_name}_%",
        )
        return len(rows)
    finally:
        conn.close()


def _build_table_metadata_block(source: dict, table: dict) -> str:
    role = table.get("table_role") or "fact"
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
    return "\n".join(lines)


def build_catalog_metadata_text(source: dict) -> list[dict[str, str]]:
    """One text block per RAG-enabled cataloged table (+ dataset overview)."""
    blocks: list[dict[str, str]] = []
    definition_md = load_definition_for_prompt(source)
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
        if not should_rag_table(table):
            continue
        blocks.append({"key": table["table_name"], "text": _build_table_metadata_block(source, table)})

    return blocks


def _is_lookup_table(table: dict) -> bool:
    return should_rag_table(table) and (table.get("table_role") or "fact") == "lookup"


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

    chunk_size, chunk_overlap = _table_chunk_settings(table, profile)
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
                    "table_metadata_id": table["id"],
                }
            )
    return items


def index_structured_catalog(
    source: dict,
    embedder,
    *,
    replace_existing: bool = True,
    table_ids: list[str] | None = None,
) -> dict:
    """
    Embed catalog metadata (and lookup rows) into knowledge_chunks.
    When table_ids is set, only those tables are re-indexed; other disabled tables are purged.
    """
    if source.get("source_type") != "structured":
        raise ValueError("Catalog indexing applies to structured datasets only")

    profile = get_rag_profile(source["id"]) or {}
    all_tables = list_table_metadata(source["id"])
    default_chunk_size = profile.get("chunk_size") or 400
    default_chunk_overlap = profile.get("chunk_overlap") or 60
    domain_slug = source.get("domain_slug", "domain")
    source_slug = source.get("slug", "ds")
    prefix = _chunk_id_prefix(domain_slug, source_slug)
    rag_profile_id = profile.get("id")

    if table_ids is not None and len(table_ids) == 0:
        return {
            "removed_chunks": 0,
            "catalog_chunks": 0,
            "metadata_tables": 0,
            "lookup_tables": 0,
            "skipped": True,
            "source_file": CATALOG_SOURCE_PREFIX,
        }

    removed = 0
    if table_ids:
        allowed = set(table_ids)
        for table in all_tables:
            if table["id"] in allowed or not should_rag_table(table):
                removed += delete_table_rag_chunks(source, table)
        target_tables = [t for t in all_tables if t["id"] in allowed and should_rag_table(t)]
    else:
        if replace_existing:
            removed = delete_structured_rag_chunks(source)
        else:
            for table in all_tables:
                if not should_rag_table(table):
                    removed += delete_table_rag_chunks(source, table)
        target_tables = [t for t in all_tables if should_rag_table(t)]

    items: list[dict[str, Any]] = []
    overview_blocks = build_catalog_metadata_text(source)
    for block in overview_blocks:
        key = block["key"]
        if key != "_overview" and not any(t["table_name"] == key for t in target_tables):
            continue
        chunk_size = default_chunk_size
        chunk_overlap = default_chunk_overlap
        table_meta_id = None
        if key != "_overview":
            match = next((t for t in target_tables if t["table_name"] == key), None)
            if match:
                chunk_size, chunk_overlap = _table_chunk_settings(match, profile)
                table_meta_id = match["id"]
        source_file = _scoped_catalog_source_file(
            domain_slug, source_slug, "overview" if key == "_overview" else key,
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
                    "table_metadata_id": table_meta_id,
                }
            )

    for table in target_tables:
        items.extend(_lookup_row_chunks(source, table, profile))

    instructions = (profile.get("instructions") or "").strip()
    if instructions and (not table_ids or target_tables):
        for i, piece in enumerate(chunk_text(instructions, default_chunk_size, default_chunk_overlap)):
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

    written = upsert_chunks(items, embedder) if items else 0
    if profile:
        update_rag_profile(source["id"], touch_ingested=True)

    return {
        "removed_chunks": removed,
        "catalog_chunks": written,
        "metadata_tables": len(target_tables),
        "lookup_tables": sum(1 for t in target_tables if _is_lookup_table(t)),
        "source_file": CATALOG_SOURCE_PREFIX,
    }
