"""Catalog Postgres connections (metadata + RAG). Uses psycopg3 by default; pg8000 optional fallback."""

from __future__ import annotations

import os
import re
import ssl
from typing import Any

_PARAM_RE = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)(?=::|,|\)|\s|$|;)")


def catalog_db_driver() -> str:
    """psycopg (default) or pg8000 — catalog/metadata only; business SQL uses Trino."""
    value = (os.environ.get("CATALOG_DB_DRIVER") or "psycopg").strip().lower()
    return value if value in ("psycopg", "pg8000") else "psycopg"


def _ssl_context(sslmode: str):
    if sslmode in ("require", "verify-ca", "verify-full"):
        ctx = ssl.create_default_context()
        if sslmode == "require":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def _pg8000_style_to_psycopg(sql: str) -> str:
    return _PARAM_RE.sub(r"%(\1)s", sql)


class CatalogConnection:
    """pg8000-compatible `.run()` wrapper so catalog_db.py stays unchanged."""

    def __init__(self, impl: Any, *, driver: str) -> None:
        self._impl = impl
        self._driver = driver
        self.columns: list[dict[str, str]] | None = None

    def run(self, sql: str, **params: Any) -> list[tuple[Any, ...]]:
        if self._driver == "pg8000":
            result = self._impl.run(sql, **params)
            cols = getattr(self._impl, "columns", None) or []
            self.columns = [
                c if isinstance(c, dict) else {"name": str(c)}
                for c in cols
            ]
            return result

        import psycopg

        converted = _pg8000_style_to_psycopg(sql)
        with self._impl.cursor() as cur:
            cur.execute(converted, params or None)
            if cur.description:
                self.columns = [{"name": d.name} for d in cur.description]
                rows = cur.fetchall()
                self._impl.commit()
                return rows
            self._impl.commit()
            self.columns = None
            return []

    def close(self) -> None:
        self._impl.close()


def connect_catalog(cfg: dict[str, Any]) -> CatalogConnection:
    driver = catalog_db_driver()
    if driver == "pg8000":
        import pg8000.native

        conn = pg8000.native.Connection(
            user=cfg["user"],
            password=cfg["password"],
            host=cfg["host"],
            port=int(cfg["port"]),
            database=cfg["database"],
            ssl_context=_ssl_context(cfg.get("sslmode") or "require"),
            timeout=15,
        )
        return CatalogConnection(conn, driver="pg8000")

    import psycopg

    sslmode = (cfg.get("sslmode") or "require").strip() or "require"
    conninfo = (
        f"host={cfg['host']} port={int(cfg['port'])} dbname={cfg['database']} "
        f"user={cfg['user']} password={cfg['password']} sslmode={sslmode} "
        f"connect_timeout=15"
    )
    conn = psycopg.connect(conninfo)
    conn.autocommit = False
    return CatalogConnection(conn, driver="psycopg")
