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
    cfg = dict(source.get("config") or {})
    if not cfg:
        cfg = dict(source)
    resolved: dict[str, Any] = {}
    connection_id = str(cfg.get("connection_id") or "").strip()
    if connection_id:
        try:
            from connections_service import connection_config

            resolved = connection_config(connection_id)
        except Exception:
            try:
                from connections_service import get_connection

                saved = get_connection(connection_id) or {}
                if saved:
                    resolved = {
                        "host": saved.get("host") or "",
                        "port": int(saved.get("port") or 5432),
                        "user": saved.get("user") or "",
                        "password": saved.get("password") or "",
                        "database": saved.get("database") or "postgres",
                        "schema": saved.get("schema") or "public",
                        "sslmode": saved.get("sslmode") or "require",
                    }
            except Exception:
                resolved = {}
    if not resolved:
        try:
            from connections_service import get_connection, get_connection_by_name, list_connections

            connection_name = str(cfg.get("connection_name") or "").strip()
            saved = get_connection_by_name(connection_name) if connection_name else None
            if not saved:
                postgres_rows = [row for row in list_connections() if (row.get("connector") or "").strip().lower() == "postgres"]
                if len(postgres_rows) == 1:
                    saved = get_connection(str(postgres_rows[0].get("id") or ""))
            if saved:
                resolved = {
                    "host": saved.get("host") or "",
                    "port": int(saved.get("port") or 5432),
                    "user": saved.get("user") or "",
                    "password": saved.get("password") or "",
                    "database": saved.get("database") or "postgres",
                    "schema": saved.get("schema") or "public",
                    "sslmode": saved.get("sslmode") or "require",
                }
        except Exception:
            pass
    merged = dict(resolved)
    for key, value in cfg.items():
        if value is None:
            continue
        if isinstance(value, str):
            # Keep saved-connection values when dataset config contains blank placeholders.
            if key in {"host", "user", "password", "database", "sslmode", "schema"} and not value.strip():
                continue
            merged[key] = value
            continue
        if key == "port":
            try:
                if str(value).strip():
                    merged[key] = int(value)
            except Exception:
                continue
            continue
        merged[key] = value
    return {
        "host": merged.get("host", ""),
        "port": int(merged.get("port") or 5432),
        "user": merged.get("user", ""),
        "password": merged.get("password", ""),
        "database": merged.get("database") or "postgres",
        "schema": merged.get("schema") or "public",
        "sslmode": merged.get("sslmode") or "require",
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
    """Return (connection config, kind) for structured SQL datasets."""
    connector = (source.get("connector") or "").strip().lower()
    if connector == "trino":
        from structured_trino import trino_config_from_source

        return trino_config_from_source(source), "trino"
    if connector == "postgres":
        return postgres_config_from_source(source), "postgres"
    raise ValueError(f"Unsupported structured connector: {connector}")


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
