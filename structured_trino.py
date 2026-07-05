"""Trino client for business structured SQL — introspection and read-only execution."""

from __future__ import annotations

import re
from typing import Any

import requests
from trino.auth import BasicAuthentication
from trino.dbapi import connect

from serde import coerce_json_rows
from trino_settings import get_trino_settings

_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _quote_ident(name: str) -> str:
    if _IDENT_RE.match(name):
        return name
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _qualified_schema(catalog: str, schema: str) -> str:
    return f"{_quote_ident(catalog)}.{_quote_ident(schema)}"


def _qualified_table(catalog: str, schema: str, table: str) -> str:
    return f"{_qualified_schema(catalog, schema)}.{_quote_ident(table)}"


def trino_config_from_source(source: dict) -> dict[str, Any]:
    """Dataset config + global Trino coordinator settings."""
    cfg = dict(source.get("config") or {})
    catalog = (cfg.get("catalog") or cfg.get("trino_catalog") or "").strip()
    schema = (cfg.get("schema") or "public").strip() or "public"
    if not catalog:
        raise ValueError(
            "Dataset is missing Trino catalog. Re-link the dataset to a business connection "
            "in Settings → Database connections."
        )
    return {
        **get_trino_settings(),
        "catalog": catalog,
        "schema": schema,
    }


def trino_config_from_connection(payload: dict) -> dict[str, Any]:
    catalog = (payload.get("catalog") or "").strip()
    schema = (payload.get("schema") or "public").strip() or "public"
    if not catalog:
        raise ValueError("Trino catalog name is required.")
    return {
        **get_trino_settings(),
        "catalog": catalog,
        "schema": schema,
    }


def _connect_trino(config: dict):
    auth = None
    password = config.get("password") or ""
    user = config.get("user") or "trino"
    if password:
        auth = BasicAuthentication(user, password)
    return connect(
        host=config["host"],
        port=int(config["port"]),
        user=user,
        catalog=config.get("catalog"),
        schema=config.get("schema"),
        http_scheme=config.get("http_scheme") or "http",
        auth=auth,
        verify=bool(config.get("verify_ssl")),
    )


def _trino_info_url(config: dict) -> str:
    scheme = config.get("http_scheme") or "http"
    host = config.get("host")
    port = int(config.get("port") or 8081)
    return f"{scheme}://{host}:{port}/v1/info"


def _preflight_trino_endpoint(config: dict) -> tuple[bool, str | None]:
    info_url = _trino_info_url(config)
    try:
        res = requests.get(info_url, timeout=3, verify=bool(config.get("verify_ssl")))
    except requests.RequestException as exc:
        return False, (
            f"Could not reach Trino coordinator at {info_url}: {exc}. "
            "Start Trino or update TRINO_HOST/TRINO_PORT in Settings."
        )
    if res.status_code != 200:
        return False, (
            f"Endpoint {info_url} returned HTTP {res.status_code}. "
            "This host/port is not a Trino coordinator."
        )
    return True, None


def test_trino_catalog(config: dict) -> tuple[bool, str]:
    ok, preflight_msg = _preflight_trino_endpoint(config)
    if not ok:
        return False, preflight_msg or "Trino coordinator preflight failed."
    try:
        conn = _connect_trino(config)
        try:
            cur = conn.cursor()
            cur.execute(f"SHOW TABLES FROM {_qualified_schema(config['catalog'], config['schema'])}")
            cur.fetchmany(1)
        finally:
            conn.close()
        return True, f"Trino catalog «{config['catalog']}» / schema «{config['schema']}» is reachable."
    except Exception as exc:
        return False, str(exc)


def test_trino_server(config: dict | None = None) -> tuple[bool, str]:
    """Ping the Trino coordinator (no business catalog required)."""
    base = dict(config or get_trino_settings())
    ok, preflight_msg = _preflight_trino_endpoint(base)
    if not ok:
        return False, preflight_msg or "Trino coordinator preflight failed."
    base["catalog"] = "system"
    base["schema"] = "runtime"
    try:
        conn = _connect_trino(base)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            conn.close()
        return True, "Trino coordinator is reachable."
    except Exception as exc:
        return False, str(exc)


def list_schema_tables(config: dict) -> list[str]:
    conn = _connect_trino(config)
    try:
        cur = conn.cursor()
        cur.execute(f"SHOW TABLES FROM {_qualified_schema(config['catalog'], config['schema'])}")
        rows = cur.fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def list_table_columns(config: dict, table_name: str) -> list[dict[str, Any]]:
    conn = _connect_trino(config)
    try:
        cur = conn.cursor()
        cur.execute(
            f"DESCRIBE {_qualified_table(config['catalog'], config['schema'], table_name)}"
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        col_name = str(row[0])
        data_type = str(row[1]) if len(row) > 1 else "?"
        extra = str(row[2]).lower() if len(row) > 2 and row[2] is not None else ""
        nullable = "not null" not in extra
        if col_name and not col_name.startswith("#"):
            out.append(
                {
                    "column_name": col_name,
                    "data_type": data_type,
                    "nullable": nullable,
                }
            )
    return out


def list_foreign_keys(config: dict) -> list[dict[str, Any]]:
    """FK metadata is connector-dependent; not all Trino catalogs expose referential_constraints."""
    return []


def execute_readonly_trino_sql(config: dict, sql: str, *, max_rows: int = 500) -> tuple[list[str], list[list[Any]]]:
    limited = f"SELECT * FROM ({sql.rstrip(';')}) AS _q LIMIT {max_rows}"
    ok, preflight_msg = _preflight_trino_endpoint(config)
    if not ok:
        raise RuntimeError(preflight_msg or "Trino coordinator preflight failed.")
    conn = _connect_trino(config)
    try:
        cur = conn.cursor()
        cur.execute(limited)
        rows = cur.fetchall()
        col_names = [d[0] for d in (cur.description or [])]
        if not rows:
            return col_names, []
        return col_names, coerce_json_rows([list(r) for r in rows])
    except Exception as exc:
        msg = str(exc)
        if "404" in msg:
            raise RuntimeError(
                f"Trino query endpoint returned HTTP 404 at {_trino_info_url(config)}. "
                "Verify TRINO_HOST/TRINO_PORT points to a running Trino coordinator."
            ) from exc
        raise
    finally:
        conn.close()
