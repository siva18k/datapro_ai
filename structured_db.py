"""Read-only introspection and connection tests for external Postgres sources."""

from __future__ import annotations

import ssl
from typing import Any

import pg8000.native


def _ssl_context(sslmode: str):
    if sslmode in ("require", "verify-ca", "verify-full"):
        ctx = ssl.create_default_context()
        if sslmode == "require":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def _connect_external(config: dict) -> pg8000.native.Connection:
    host = config.get("host") or ""
    port = int(config.get("port") or 5432)
    user = config.get("user") or ""
    password = config.get("password") or ""
    database = config.get("database") or "postgres"
    sslmode = config.get("sslmode") or "require"
    if not all([host, user, database]):
        raise ValueError("Host, user, and database are required.")
    return pg8000.native.Connection(
        user=user,
        password=password,
        host=host,
        port=port,
        database=database,
        ssl_context=_ssl_context(sslmode),
        timeout=15,
    )


def postgres_config_from_source(source: dict) -> dict:
    from connections_service import connection_config, resolve_saved_connection

    cfg = dict(source.get("config") or {})
    saved = resolve_saved_connection(source)
    if not saved:
        raise ValueError(
            "This dataset is not linked to a Settings connection. "
            "Open the dataset Connection tab and choose a saved connection."
        )
    connector = (saved.get("connector") or "").strip().lower()
    if connector != "postgres":
        raise ValueError("This Settings connection is Trino. Ask/Analytics will use Trino, not a direct Postgres login.")
    resolved = connection_config(str(saved.get("id") or ""))
    schema = str(cfg.get("schema") or resolved.get("schema") or "public").strip() or "public"
    return {
        "host": resolved.get("host", ""),
        "port": int(resolved.get("port") or 5432),
        "user": resolved.get("user", ""),
        "password": resolved.get("password", ""),
        "database": resolved.get("database") or "postgres",
        "schema": schema,
        "sslmode": resolved.get("sslmode") or "require",
    }


def test_postgres_connection(config: dict) -> tuple[bool, str]:
    try:
        conn = _connect_external(config)
        try:
            conn.run("SELECT 1")
        finally:
            conn.close()
        return True, "Connection successful."
    except Exception as exc:
        return False, str(exc)


def list_schema_tables(config: dict) -> list[str]:
    schema = config.get("schema") or "public"
    conn = _connect_external(config)
    try:
        rows = conn.run(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = :schema
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            schema=schema,
        )
    finally:
        conn.close()
    return [row[0] for row in rows]


def list_table_columns(config: dict, table_name: str) -> list[dict[str, Any]]:
    schema = config.get("schema") or "public"
    conn = _connect_external(config)
    try:
        rows = conn.run(
            """
            SELECT column_name, data_type, is_nullable, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table_name
            ORDER BY ordinal_position
            """,
            schema=schema,
            table_name=table_name,
        )
    finally:
        conn.close()
    return [
        {
            "column_name": row[0],
            "data_type": row[1],
            "nullable": row[2] == "YES",
        }
        for row in rows
    ]


def list_foreign_keys(config: dict) -> list[dict[str, Any]]:
    """Foreign-key constraints in the configured schema."""
    schema = config.get("schema") or "public"
    conn = _connect_external(config)
    try:
        rows = conn.run(
            """
            SELECT
                kcu.table_schema,
                kcu.table_name,
                kcu.column_name,
                ccu.table_schema AS foreign_table_schema,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_schema = kcu.constraint_schema
             AND tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_schema = tc.constraint_schema
             AND ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND kcu.table_schema = :schema
            ORDER BY kcu.table_name, kcu.column_name
            """,
            schema=schema,
        )
    finally:
        conn.close()
    return [
        {
            "table_schema": row[0],
            "table_name": row[1],
            "column_name": row[2],
            "foreign_table_schema": row[3],
            "foreign_table_name": row[4],
            "foreign_column_name": row[5],
        }
        for row in rows
    ]


def structured_runtime_config(source: dict) -> tuple[dict, str]:
    """Return (connection config, kind) using the Settings connection, not per-dataset credentials."""
    from connections_service import resolve_saved_connection
    from structured_trino import trino_config_from_source

    saved = resolve_saved_connection(source)
    if not saved:
        raise ValueError(
            "This dataset is not linked to a Settings connection. "
            "Open the dataset Connection tab and choose a saved connection."
        )
    kind = (saved.get("connector") or "").strip().lower()
    if kind == "trino":
        return trino_config_from_source(source), "trino"
    if kind == "postgres":
        return postgres_config_from_source(source), "postgres"
    raise ValueError(f"Unsupported Settings connection type: {kind or 'unknown'}")


def list_schema_tables_for_source(source: dict) -> list[str]:
    cfg, kind = structured_runtime_config(source)
    if kind == "trino":
        from structured_trino import list_schema_tables as trino_list_tables

        return trino_list_tables(cfg)
    return list_schema_tables(cfg)


def list_table_columns_for_source(source: dict, table_name: str) -> list[dict[str, Any]]:
    cfg, kind = structured_runtime_config(source)
    if kind == "trino":
        from structured_trino import list_table_columns as trino_list_columns

        return trino_list_columns(cfg, table_name)
    return list_table_columns(cfg, table_name)


def list_foreign_keys_for_source(source: dict) -> list[dict[str, Any]]:
    cfg, kind = structured_runtime_config(source)
    if kind == "trino":
        from structured_trino import list_foreign_keys as trino_list_fks

        return trino_list_fks(cfg)
    return list_foreign_keys(cfg)
