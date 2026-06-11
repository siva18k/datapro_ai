"""Postgres catalog: domains, data sources, RAG profiles, MCP bindings."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from db import connect, knowledge_chunks_has_catalog_columns

PROJECT_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = PROJECT_DIR / "migrations"


def _invalidate_routing_cache() -> None:
    try:
        from routing_cache import clear_routing_cache

        clear_routing_cache()
    except Exception:
        pass

DEFAULT_DOMAINS = [
    {
        "slug": "general",
        "name": "General",
        "description": "Legacy and cross-domain documents.",
        "color": "#6b7280",
    },
    {
        "slug": "hr",
        "name": "HR",
        "description": "Human resources policies, employee handbooks, benefits, and HR procedures.",
        "color": "#059669",
    },
    {
        "slug": "finance",
        "name": "Finance",
        "description": "Financial policies, budgets, accounting procedures, and expense rules.",
        "color": "#2563eb",
    },
    {
        "slug": "sales",
        "name": "Sales",
        "description": "Sales playbooks, pricing, contracts, and customer-facing policies.",
        "color": "#d97706",
    },
]

DEFAULT_SOURCES = [
    {
        "domain_slug": "general",
        "slug": "sample_docs",
        "name": "Sample Documents",
        "description": "Default sample_docs folder for legacy ingestion.",
        "source_type": "unstructured",
        "connector": "file_path",
        "config": {"path": "sample_docs"},
    },
    {
        "domain_slug": "hr",
        "slug": "hr_policies",
        "name": "HR Policies",
        "description": "HR policy documents including employee handbook and travel policy.",
        "source_type": "unstructured",
        "connector": "file_path",
        "config": {"path": "sample_docs"},
    },
    {
        "domain_slug": "finance",
        "slug": "finance_docs",
        "name": "Finance Documents",
        "description": "Finance policies and reference documents.",
        "source_type": "unstructured",
        "connector": "upload",
        "config": {"path": "data/finance/finance_docs"},
    },
    {
        "domain_slug": "sales",
        "slug": "sales_docs",
        "name": "Sales Documents",
        "description": "Sales playbooks and customer documentation.",
        "source_type": "unstructured",
        "connector": "upload",
        "config": {"path": "data/sales/sales_docs"},
    },
]

DEFAULT_MCP_BINDINGS = [
    ("search_documents", "tool"),
    ("list_domain_sources", "tool"),
    ("domain_grounded_answer", "prompt"),
    ("ragpro://domains", "resource"),
]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "item"


def _coerce_jsonb_list(value: Any, *, default: list | None = None) -> list:
    """Parse JSONB list columns; pg8000 may return list or str."""
    if value is None:
        return list(default) if default is not None else []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        if not value.strip():
            return []
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    return list(default) if default is not None else []


def _row_to_dict(columns: list[str], row: tuple) -> dict[str, Any]:
    return {col: row[i] for i, col in enumerate(columns)}


def apply_migrations() -> dict[str, bool]:
    """Apply SQL migrations. Returns flags for optional steps that could not run."""
    skipped_chunks_alter = False
    conn, schema = connect()
    try:
        conn.run(f"SET search_path TO {_quote_ident(schema)}")
        for migration_name in (
            "000_vector_base.sql",
            "001_catalog.sql",
            "002_knowledge_chunks_catalog.sql",
            "003_structured_metadata.sql",
            "004_table_roles.sql",
        ):
            migration = MIGRATIONS_DIR / migration_name
            if not migration.exists():
                continue
            sql = migration.read_text(encoding="utf-8")
            for statement in _split_sql(sql):
                if not statement.strip():
                    continue
                try:
                    conn.run(statement)
                except Exception as exc:
                    if migration_name.startswith("002"):
                        skipped_chunks_alter = True
                    else:
                        raise
    finally:
        conn.close()
    return {"skipped_knowledge_chunks_alter": skipped_chunks_alter}


def _quote_ident(name: str) -> str:
    return f'"{name}"'


def _split_sql(sql: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            parts.append("\n".join(current))
            current = []
    if current:
        parts.append("\n".join(current))
    return parts


def ensure_catalog_seeded() -> None:
    conn, schema = connect()
    try:
        rows = conn.run(f"SELECT COUNT(*) FROM {schema}.domains")
        if rows and rows[0][0] > 0:
            _migrate_legacy_chunks(conn, schema)
            return

        domain_ids: dict[str, str] = {}
        for domain in DEFAULT_DOMAINS:
            domain_id = _insert_domain(conn, schema, domain)
            domain_ids[domain["slug"]] = domain_id

        source_ids: dict[str, str] = {}
        for source in DEFAULT_SOURCES:
            domain_id = domain_ids[source["domain_slug"]]
            source_id = _insert_source(conn, schema, domain_id, source)
            source_ids[source["slug"]] = source_id
            _insert_rag_profile(conn, schema, source_id, source.get("instructions", ""))

        for domain_id in domain_ids.values():
            for cap_name, cap_type in DEFAULT_MCP_BINDINGS:
                _upsert_binding(conn, schema, domain_id, None, cap_type, cap_name, True)

        _migrate_legacy_chunks(conn, schema, domain_ids, source_ids)
    finally:
        conn.close()


def _insert_domain(conn, schema: str, domain: dict) -> str:
    rows = conn.run(
        f"""
        INSERT INTO {schema}.domains (slug, name, description, color, enabled)
        VALUES (:slug, :name, :description, :color, TRUE)
        ON CONFLICT (slug) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            updated_at = now()
        RETURNING id::text
        """,
        slug=domain["slug"],
        name=domain["name"],
        description=domain["description"],
        color=domain.get("color", "#2563eb"),
    )
    return rows[0][0]


def _insert_source(conn, schema: str, domain_id: str, source: dict) -> str:
    rows = conn.run(
        f"""
        INSERT INTO {schema}.data_sources
            (domain_id, slug, name, description, source_type, connector, config, enabled)
        VALUES
            (:domain_id::uuid, :slug, :name, :description, :source_type, :connector,
             :config::jsonb, TRUE)
        ON CONFLICT (domain_id, slug) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            updated_at = now()
        RETURNING id::text
        """,
        domain_id=domain_id,
        slug=source["slug"],
        name=source["name"],
        description=source["description"],
        source_type=source["source_type"],
        connector=source["connector"],
        config=json.dumps(source.get("config", {})),
    )
    return rows[0][0]


def _insert_rag_profile(conn, schema: str, source_id: str, instructions: str = "") -> str:
    rows = conn.run(
        f"""
        INSERT INTO {schema}.rag_profiles (source_id, instructions)
        VALUES (:source_id::uuid, :instructions)
        ON CONFLICT (source_id) DO UPDATE SET updated_at = now()
        RETURNING id::text
        """,
        source_id=source_id,
        instructions=instructions,
    )
    return rows[0][0]


def _upsert_binding(
    conn,
    schema: str,
    domain_id: str | None,
    source_id: str | None,
    capability_type: str,
    capability_name: str,
    enabled: bool,
) -> None:
    conn.run(
        f"""
        INSERT INTO {schema}.mcp_bindings
            (domain_id, source_id, capability_type, capability_name, enabled)
        VALUES
            (:domain_id::uuid, :source_id::uuid, :capability_type, :capability_name, :enabled)
        ON CONFLICT (domain_id, source_id, capability_type, capability_name)
        DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now()
        """,
        domain_id=domain_id,
        source_id=source_id,
        capability_type=capability_type,
        capability_name=capability_name,
        enabled=enabled,
    )


def _migrate_legacy_chunks(
    conn,
    schema: str,
    domain_ids: dict[str, str] | None = None,
    source_ids: dict[str, str] | None = None,
) -> None:
    if domain_ids is None:
        rows = conn.run(
            f"SELECT id::text, slug FROM {schema}.domains WHERE slug = 'general'"
        )
        if not rows:
            return
        domain_ids = {"general": rows[0][0]}
        src_rows = conn.run(
            f"""
            SELECT id::text, slug FROM {schema}.data_sources
            WHERE domain_id = :domain_id::uuid AND slug = 'sample_docs'
            """,
            domain_id=domain_ids["general"],
        )
        source_ids = {"sample_docs": src_rows[0][0]} if src_rows else {}

    general_id = domain_ids.get("general")
    sample_id = source_ids.get("sample_docs")
    if not general_id or not knowledge_chunks_has_catalog_columns():
        return

    conn.run(
        f"""
        UPDATE {schema}.knowledge_chunks
        SET domain_id = COALESCE(domain_id, :domain_id::uuid),
            source_id = COALESCE(source_id, :source_id::uuid)
        WHERE domain_id IS NULL
        """,
        domain_id=general_id,
        source_id=sample_id,
    )


def init_catalog() -> None:
    """Ensure migrations and seed data exist (safe to call on every page load)."""
    try:
        conn, schema = connect()
        try:
            conn.run(f"SELECT 1 FROM {schema}.domains LIMIT 1")
        except Exception:
            apply_migrations()
            ensure_catalog_seeded()
            return
        finally:
            conn.close()
        ensure_catalog_seeded()
    except Exception:
        pass


# --- CRUD ---


def list_domains(*, enabled_only: bool = True) -> list[dict]:
    conn, schema = connect()
    try:
        where = "WHERE enabled = TRUE" if enabled_only else ""
        rows = conn.run(
            f"""
            SELECT id::text, slug, name, description, color, enabled,
                   created_at, updated_at
            FROM {schema}.domains
            {where}
            ORDER BY name
            """
        )
    finally:
        conn.close()
    cols = ["id", "slug", "name", "description", "color", "enabled", "created_at", "updated_at"]
    return [_row_to_dict(cols, row) for row in rows]


def get_domain(*, domain_id: str | None = None, slug: str | None = None) -> dict | None:
    conn, schema = connect()
    try:
        if domain_id:
            rows = conn.run(
                f"""
                SELECT id::text, slug, name, description, color, enabled
                FROM {schema}.domains WHERE id = :id::uuid
                """,
                id=domain_id,
            )
        elif slug:
            rows = conn.run(
                f"""
                SELECT id::text, slug, name, description, color, enabled
                FROM {schema}.domains WHERE slug = :slug
                """,
                slug=slug,
            )
        else:
            return None
    finally:
        conn.close()
    if not rows:
        return None
    cols = ["id", "slug", "name", "description", "color", "enabled"]
    return _row_to_dict(cols, rows[0])


def create_domain(name: str, description: str = "", color: str = "#2563eb") -> dict:
    slug = _slugify(name)
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            INSERT INTO {schema}.domains (slug, name, description, color)
            VALUES (:slug, :name, :description, :color)
            RETURNING id::text, slug, name, description, color, enabled
            """,
            slug=slug,
            name=name,
            description=description,
            color=color,
        )
        domain_id = rows[0][0]
        for cap_name, cap_type in DEFAULT_MCP_BINDINGS:
            _upsert_binding(conn, schema, domain_id, None, cap_type, cap_name, True)
    finally:
        conn.close()
    cols = ["id", "slug", "name", "description", "color", "enabled"]
    out = _row_to_dict(cols, rows[0])
    _invalidate_routing_cache()
    return out


def update_domain(domain_id: str, **fields) -> None:
    allowed = {"name", "description", "color", "enabled"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return
    sets = ", ".join(f"{k} = :{k}" for k in updates)
    conn, schema = connect()
    try:
        conn.run(
            f"""
            UPDATE {schema}.domains SET {sets}, updated_at = now()
            WHERE id = :id::uuid
            """,
            id=domain_id,
            **updates,
        )
    finally:
        conn.close()


def delete_domain(domain_id: str) -> bool:
    """Remove a domain only when it has no datasets (data_sources)."""
    sources = list_sources(domain_id=domain_id, enabled_only=False)
    if sources:
        preview = ", ".join(s["name"] for s in sources[:5])
        if len(sources) > 5:
            preview += f", +{len(sources) - 5} more"
        raise ValueError(
            f"Cannot delete domain: {len(sources)} dataset(s) still exist ({preview}). "
            "Delete all datasets in this domain first."
        )
    conn, schema = connect()
    try:
        rows = conn.run(
            f"DELETE FROM {schema}.domains WHERE id = :id::uuid RETURNING id::text",
            id=domain_id,
        )
        return bool(rows)
    finally:
        conn.close()


def list_sources(
    domain_id: str | None = None,
    *,
    enabled_only: bool = True,
    source_type: str | None = None,
) -> list[dict]:
    conn, schema = connect()
    clauses = []
    params: dict[str, Any] = {}
    if domain_id:
        clauses.append("s.domain_id = :domain_id::uuid")
        params["domain_id"] = domain_id
    if enabled_only:
        clauses.append("s.enabled = TRUE")
    if source_type:
        clauses.append("s.source_type = :source_type")
        params["source_type"] = source_type
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        rows = conn.run(
            f"""
            SELECT s.id::text, s.domain_id::text, d.slug AS domain_slug, d.name AS domain_name,
                   s.slug, s.name, s.description, s.source_type, s.connector,
                   s.config::text, s.enabled, s.created_at, s.updated_at
            FROM {schema}.data_sources s
            JOIN {schema}.domains d ON d.id = s.domain_id
            {where}
            ORDER BY d.name, s.name
            """,
            **params,
        )
    finally:
        conn.close()
    cols = [
        "id", "domain_id", "domain_slug", "domain_name", "slug", "name", "description",
        "source_type", "connector", "config", "enabled", "created_at", "updated_at",
    ]
    results = []
    for row in rows:
        item = _row_to_dict(cols, row)
        item["config"] = json.loads(item["config"] or "{}")
        results.append(item)
    return results


def get_source(*, source_id: str | None = None, slug: str | None = None, domain_id: str | None = None) -> dict | None:
    conn, schema = connect()
    try:
        if source_id:
            rows = conn.run(
                f"""
                SELECT s.id::text, s.domain_id::text, d.slug AS domain_slug, d.name AS domain_name,
                       s.slug, s.name, s.description, s.source_type, s.connector,
                       s.config::text, s.enabled
                FROM {schema}.data_sources s
                JOIN {schema}.domains d ON d.id = s.domain_id
                WHERE s.id = :id::uuid
                """,
                id=source_id,
            )
        elif slug and domain_id:
            rows = conn.run(
                f"""
                SELECT s.id::text, s.domain_id::text, d.slug AS domain_slug, d.name AS domain_name,
                       s.slug, s.name, s.description, s.source_type, s.connector,
                       s.config::text, s.enabled
                FROM {schema}.data_sources s
                JOIN {schema}.domains d ON d.id = s.domain_id
                WHERE s.slug = :slug AND s.domain_id = :domain_id::uuid
                """,
                slug=slug,
                domain_id=domain_id,
            )
        else:
            return None
    finally:
        conn.close()
    if not rows:
        return None
    cols = [
        "id", "domain_id", "domain_slug", "domain_name", "slug", "name", "description",
        "source_type", "connector", "config", "enabled",
    ]
    item = _row_to_dict(cols, rows[0])
    item["config"] = json.loads(item["config"] or "{}")
    return item


def create_source(
    domain_id: str,
    name: str,
    *,
    description: str = "",
    source_type: str = "unstructured",
    connector: str = "upload",
    config: dict | None = None,
) -> dict:
    domain = get_domain(domain_id=domain_id)
    if not domain:
        raise ValueError("Domain not found")
    slug = _slugify(name)
    cfg = config or {}
    if connector == "upload" and "path" not in cfg:
        cfg["path"] = f"data/{domain['slug']}/{slug}"
    if connector == "postgres" and "schema" not in cfg:
        cfg["schema"] = "public"
    if connector in ("sharepoint", "web_url") and "url" not in cfg:
        cfg["url"] = ""
    if connector == "api" and "base_url" not in cfg:
        cfg["base_url"] = ""
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            INSERT INTO {schema}.data_sources
                (domain_id, slug, name, description, source_type, connector, config)
            VALUES
                (:domain_id::uuid, :slug, :name, :description, :source_type, :connector, :config::jsonb)
            RETURNING id::text
            """,
            domain_id=domain_id,
            slug=slug,
            name=name,
            description=description,
            source_type=source_type,
            connector=connector,
            config=json.dumps(cfg),
        )
        source_id = rows[0][0]
        _insert_rag_profile(conn, schema, source_id)
    finally:
        conn.close()
    _invalidate_routing_cache()
    return get_source(source_id=source_id)  # type: ignore[return-value]


def update_source(source_id: str, **fields) -> None:
    allowed = {"name", "description", "config", "enabled", "connector"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "config" in updates and isinstance(updates["config"], dict):
        updates["config"] = json.dumps(updates["config"])
    if not updates:
        return
    sets = ", ".join(
        f"{k} = :{k}::jsonb" if k == "config" else f"{k} = :{k}" for k in updates
    )
    conn, schema = connect()
    try:
        conn.run(
            f"""
            UPDATE {schema}.data_sources SET {sets}, updated_at = now()
            WHERE id = :id::uuid
            """,
            id=source_id,
            **updates,
        )
    finally:
        conn.close()
    _invalidate_routing_cache()


def delete_source(source_id: str) -> bool:
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            DELETE FROM {schema}.data_sources
            WHERE id = :id::uuid
            RETURNING id::text
            """,
            id=source_id,
        )
    finally:
        conn.close()
    deleted = bool(rows)
    if deleted:
        _invalidate_routing_cache()
    return deleted


def get_rag_profile(source_id: str) -> dict | None:
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            SELECT id::text, source_id::text, chunk_size, chunk_overlap, embedding_model,
                   instructions, metadata_text, last_ingested_at, updated_at
            FROM {schema}.rag_profiles
            WHERE source_id = :source_id::uuid
            """,
            source_id=source_id,
        )
    finally:
        conn.close()
    if not rows:
        return None
    cols = [
        "id", "source_id", "chunk_size", "chunk_overlap", "embedding_model",
        "instructions", "metadata_text", "last_ingested_at", "updated_at",
    ]
    return _row_to_dict(cols, rows[0])


def update_rag_profile(source_id: str, **fields) -> None:
    allowed = {
        "chunk_size", "chunk_overlap", "embedding_model",
        "instructions", "metadata_text",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    touch_ingested = fields.get("touch_ingested", False)
    if not updates and not touch_ingested:
        return
    extra = ", last_ingested_at = now()" if touch_ingested else ""
    sets = ", ".join(f"{k} = :{k}" for k in updates)
    set_clause = sets + extra if sets else extra.lstrip(", ")
    conn, schema = connect()
    try:
        conn.run(
            f"""
            UPDATE {schema}.rag_profiles SET {set_clause}, updated_at = now()
            WHERE source_id = :source_id::uuid
            """,
            source_id=source_id,
            **updates,
        )
    finally:
        conn.close()


def list_mcp_bindings(domain_id: str | None = None) -> list[dict]:
    conn, schema = connect()
    try:
        if domain_id:
            rows = conn.run(
                f"""
                SELECT id::text, domain_id::text, source_id::text, capability_type,
                       capability_name, enabled
                FROM {schema}.mcp_bindings
                WHERE domain_id = :domain_id::uuid OR domain_id IS NULL
                ORDER BY capability_type, capability_name
                """,
                domain_id=domain_id,
            )
        else:
            rows = conn.run(
                f"""
                SELECT id::text, domain_id::text, source_id::text, capability_type,
                       capability_name, enabled
                FROM {schema}.mcp_bindings
                ORDER BY capability_type, capability_name
                """
            )
    finally:
        conn.close()
    cols = ["id", "domain_id", "source_id", "capability_type", "capability_name", "enabled"]
    return [_row_to_dict(cols, row) for row in rows]


def set_mcp_binding(
    domain_id: str | None,
    capability_type: str,
    capability_name: str,
    enabled: bool,
    source_id: str | None = None,
) -> None:
    conn, schema = connect()
    try:
        _upsert_binding(conn, schema, domain_id, source_id, capability_type, capability_name, enabled)
    finally:
        conn.close()


def is_capability_enabled_for_domain(domain_id: str, capability_type: str, capability_name: str) -> bool:
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            SELECT enabled FROM {schema}.mcp_bindings
            WHERE domain_id = :domain_id::uuid
              AND capability_type = :capability_type
              AND capability_name = :capability_name
              AND source_id IS NULL
            LIMIT 1
            """,
            domain_id=domain_id,
            capability_type=capability_type,
            capability_name=capability_name,
        )
    finally:
        conn.close()
    if not rows:
        return True
    return bool(rows[0][0])


def get_domain_stats(domain_slug: str | None = None) -> list[dict]:
    conn, schema = connect()
    try:
        if domain_slug:
            rows = conn.run(
                f"""
                SELECT d.slug, d.name, s.slug AS source_slug, s.name AS source_name,
                       COUNT(k.id) AS chunk_count
                FROM {schema}.domains d
                LEFT JOIN {schema}.data_sources s ON s.domain_id = d.id
                LEFT JOIN {schema}.knowledge_chunks k ON k.source_id = s.id
                WHERE d.slug = :slug
                GROUP BY d.slug, d.name, s.slug, s.name
                ORDER BY s.name
                """,
                slug=domain_slug,
            )
        else:
            rows = conn.run(
                f"""
                SELECT d.slug, d.name, s.slug AS source_slug, s.name AS source_name,
                       COUNT(k.id) AS chunk_count
                FROM {schema}.domains d
                LEFT JOIN {schema}.data_sources s ON s.domain_id = d.id
                LEFT JOIN {schema}.knowledge_chunks k ON k.source_id = s.id
                GROUP BY d.slug, d.name, s.slug, s.name
                ORDER BY d.name, s.name
                """
            )
    finally:
        conn.close()
    cols = ["domain_slug", "domain_name", "source_slug", "source_name", "chunk_count"]
    return [_row_to_dict(cols, row) for row in rows]


def list_table_metadata(source_id: str) -> list[dict]:
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            SELECT id::text, source_id::text, table_schema, table_name, definition,
                   enabled, table_role
            FROM {schema}.table_metadata
            WHERE source_id = :source_id::uuid
            ORDER BY table_name
            """,
            source_id=source_id,
        )
    finally:
        conn.close()
    cols = [
        "id", "source_id", "table_schema", "table_name", "definition", "enabled", "table_role",
    ]
    return [_row_to_dict(cols, row) for row in rows]


def get_table_metadata(table_id: str) -> dict | None:
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            SELECT id::text, source_id::text, table_schema, table_name, definition,
                   enabled, table_role
            FROM {schema}.table_metadata WHERE id = :id::uuid
            """,
            id=table_id,
        )
    finally:
        conn.close()
    if not rows:
        return None
    cols = [
        "id", "source_id", "table_schema", "table_name", "definition", "enabled", "table_role",
    ]
    return _row_to_dict(cols, rows[0])


def upsert_table_metadata(
    source_id: str,
    table_schema: str,
    table_name: str,
    *,
    definition: str | None = None,
    enabled: bool | None = None,
) -> dict:
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            INSERT INTO {schema}.table_metadata
                (source_id, table_schema, table_name, definition)
            VALUES (:source_id::uuid, :table_schema, :table_name, :definition)
            ON CONFLICT (source_id, table_schema, table_name) DO UPDATE SET
                definition = COALESCE(:definition, {schema}.table_metadata.definition),
                enabled = COALESCE(:enabled, {schema}.table_metadata.enabled),
                updated_at = now()
            RETURNING id::text
            """,
            source_id=source_id,
            table_schema=table_schema,
            table_name=table_name,
            definition=definition or "",
            enabled=enabled,
        )
        table_id = rows[0][0]
    finally:
        conn.close()
    _invalidate_routing_cache()
    return get_table_metadata(table_id)  # type: ignore[return-value]


def update_table_metadata(table_id: str, **fields) -> None:
    allowed = {"definition", "enabled", "table_role"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    sets = ", ".join(f"{k} = :{k}" for k in updates)
    conn, schema = connect()
    try:
        conn.run(
            f"""
            UPDATE {schema}.table_metadata SET {sets}, updated_at = now()
            WHERE id = :id::uuid
            """,
            id=table_id,
            **updates,
        )
    finally:
        conn.close()
    _invalidate_routing_cache()


def delete_table_metadata(table_id: str) -> None:
    conn, schema = connect()
    try:
        conn.run(
            f"DELETE FROM {schema}.table_metadata WHERE id = :id::uuid",
            id=table_id,
        )
    finally:
        conn.close()
    _invalidate_routing_cache()


def get_column_metadata(column_id: str) -> dict | None:
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            SELECT id::text, table_metadata_id::text, column_name, data_type, labels, description
            FROM {schema}.column_metadata WHERE id = :id::uuid
            """,
            id=column_id,
        )
    finally:
        conn.close()
    if not rows:
        return None
    cols = ["id", "table_metadata_id", "column_name", "data_type", "labels", "description"]
    item = _row_to_dict(cols, rows[0])
    item["labels"] = _coerce_jsonb_list(item.get("labels"))
    return item


def list_column_metadata(table_id: str) -> list[dict]:
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            SELECT id::text, table_metadata_id::text, column_name, data_type,
                   labels, description
            FROM {schema}.column_metadata
            WHERE table_metadata_id = :table_id::uuid
            ORDER BY column_name
            """,
            table_id=table_id,
        )
    finally:
        conn.close()
    result = []
    cols = ["id", "table_metadata_id", "column_name", "data_type", "labels", "description"]
    for row in rows:
        item = _row_to_dict(cols, row)
        item["labels"] = _coerce_jsonb_list(item.get("labels"))
        result.append(item)
    return result


def list_columns_by_source(source_id: str) -> dict[str, list[dict]]:
    """All column metadata for a dataset in one query (keyed by table_metadata_id)."""
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            SELECT c.id::text, c.table_metadata_id::text, c.column_name, c.data_type,
                   c.labels, c.description
            FROM {schema}.column_metadata c
            JOIN {schema}.table_metadata t ON t.id = c.table_metadata_id
            WHERE t.source_id = :source_id::uuid
            ORDER BY c.column_name
            """,
            source_id=source_id,
        )
    finally:
        conn.close()
    cols = ["id", "table_metadata_id", "column_name", "data_type", "labels", "description"]
    by_table: dict[str, list[dict]] = {}
    for row in rows:
        item = _row_to_dict(cols, row)
        item["labels"] = _coerce_jsonb_list(item.get("labels"))
        by_table.setdefault(item["table_metadata_id"], []).append(item)
    return by_table


def delete_column_metadata(column_id: str) -> None:
    conn, schema = connect()
    try:
        conn.run(
            f"DELETE FROM {schema}.column_metadata WHERE id = :id::uuid",
            id=column_id,
        )
    finally:
        conn.close()


def upsert_column_metadata(
    table_id: str,
    column_name: str,
    *,
    data_type: str | None = None,
    labels: list[str] | None = None,
    description: str | None = None,
) -> dict:
    conn, schema = connect()
    labels_param = json.dumps(labels) if labels is not None else None
    try:
        rows = conn.run(
            f"""
            INSERT INTO {schema}.column_metadata
                (table_metadata_id, column_name, data_type, labels, description)
            VALUES (
                :table_id::uuid,
                :column_name,
                COALESCE(:data_type, ''),
                COALESCE(:labels::jsonb, '[]'::jsonb),
                COALESCE(:description, '')
            )
            ON CONFLICT (table_metadata_id, column_name) DO UPDATE SET
                data_type = COALESCE(:data_type, {schema}.column_metadata.data_type),
                labels = COALESCE(:labels::jsonb, {schema}.column_metadata.labels),
                description = COALESCE(:description, {schema}.column_metadata.description),
                updated_at = now()
            RETURNING id::text
            """,
            table_id=table_id,
            column_name=column_name,
            data_type=data_type,
            labels=labels_param,
            description=description,
        )
        col_id = rows[0][0]
        cols = conn.run(
            f"""
            SELECT id::text, table_metadata_id::text, column_name, data_type, labels, description
            FROM {schema}.column_metadata WHERE id = :id::uuid
            """,
            id=col_id,
        )
    finally:
        conn.close()
    item = _row_to_dict(
        ["id", "table_metadata_id", "column_name", "data_type", "labels", "description"],
        cols[0],
    )
    item["labels"] = _coerce_jsonb_list(item.get("labels"))
    return item


def sync_columns_from_introspection(
    table_id: str,
    discovered_columns: list[dict],
) -> dict[str, Any]:
    """Add new columns and update changed types; preserve labels and descriptions."""
    existing = {c["column_name"]: c for c in list_column_metadata(table_id)}
    discovered_names = {col["column_name"] for col in discovered_columns}
    stats = {"added": 0, "updated": 0, "removed": 0, "unchanged": 0}

    for col in discovered_columns:
        name = col["column_name"]
        prior = existing.get(name)
        new_type = col.get("data_type", "") or ""
        if not prior:
            upsert_column_metadata(table_id, name, data_type=new_type)
            stats["added"] += 1
        elif (prior.get("data_type") or "") != new_type:
            upsert_column_metadata(table_id, name, data_type=new_type)
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1

    for name, prior in existing.items():
        if name not in discovered_names:
            delete_column_metadata(prior["id"])
            stats["removed"] += 1

    return {"columns": list_column_metadata(table_id), "stats": stats}
