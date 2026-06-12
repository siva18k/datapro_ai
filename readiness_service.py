"""Check RAG database, catalog, and metadata availability for the UI."""

from __future__ import annotations

from typing import Any

_COMPONENT_LABELS = {
    "rag_database": "RAG database",
    "knowledge_chunks": "RAG vector store",
    "catalog": "Data catalog",
    "metadata": "Structured metadata",
}


def _table_exists(conn, schema: str, table_name: str) -> bool:
    rows = conn.run(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = :schema AND table_name = :table
        LIMIT 1
        """,
        schema=schema,
        table=table_name,
    )
    return bool(rows)


def _component(ok: bool, *, message: str | None = None) -> dict[str, Any]:
    return {"ok": ok, "message": message}


def check_readiness() -> dict[str, Any]:
    """Return per-component availability and human-readable issues."""
    components: dict[str, dict[str, Any]] = {
        "rag_database": _component(False, message="Not checked"),
        "knowledge_chunks": _component(False, message="Not checked"),
        "catalog": _component(False, message="Not checked"),
        "metadata": _component(False, message="Not checked"),
    }
    issues: list[str] = []

    try:
        from db import connect, get_db_config

        cfg = get_db_config()
        conn, schema = connect()
        try:
            conn.run("SELECT 1")
            components["rag_database"] = _component(
                True,
                message=f"Connected to {cfg['database']}@{cfg['host']}:{cfg['port']}",
            )

            if _table_exists(conn, schema, "knowledge_chunks"):
                components["knowledge_chunks"] = _component(True)
            else:
                msg = "knowledge_chunks table is missing — run database migrations."
                components["knowledge_chunks"] = _component(False, message=msg)
                issues.append(f"{_COMPONENT_LABELS['knowledge_chunks']}: {msg}")

            catalog_tables = ("domains", "data_sources", "rag_profiles")
            missing_catalog = [t for t in catalog_tables if not _table_exists(conn, schema, t)]
            if not missing_catalog:
                components["catalog"] = _component(True)
            else:
                msg = f"Missing catalog tables ({', '.join(missing_catalog)}) — run migrations."
                components["catalog"] = _component(False, message=msg)
                issues.append(f"{_COMPONENT_LABELS['catalog']}: {msg}")

            metadata_tables = ("table_metadata", "column_metadata")
            missing_metadata = [t for t in metadata_tables if not _table_exists(conn, schema, t)]
            if not missing_metadata:
                components["metadata"] = _component(True)
            else:
                msg = f"Missing metadata tables ({', '.join(missing_metadata)}) — run migrations."
                components["metadata"] = _component(False, message=msg)
                issues.append(f"{_COMPONENT_LABELS['metadata']}: {msg}")
        finally:
            conn.close()
    except Exception as exc:
        msg = str(exc).strip() or "Connection failed"
        components["rag_database"] = _component(False, message=msg)
        issues.append(f"{_COMPONENT_LABELS['rag_database']}: {msg}")
        for key in ("knowledge_chunks", "catalog", "metadata"):
            components[key] = _component(False, message="Unavailable — database not reachable")

    return {
        "ok": not issues,
        "components": components,
        "issues": issues,
    }
