"""Shared helpers for structured SQL datasets (Trino; legacy direct Postgres)."""

from __future__ import annotations

STRUCTURED_SQL_CONNECTORS = frozenset({"trino", "postgres"})


def is_structured_sql_connector(connector: str | None) -> bool:
    return (connector or "").strip().lower() in STRUCTURED_SQL_CONNECTORS
