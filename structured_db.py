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
    return {
        "host": cfg.get("host", ""),
        "port": int(cfg.get("port") or 5432),
        "user": cfg.get("user", ""),
        "password": cfg.get("password", ""),
        "database": cfg.get("database") or "postgres",
        "schema": cfg.get("schema") or "public",
        "sslmode": cfg.get("sslmode") or "require",
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
