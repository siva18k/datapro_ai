"""Trino query-engine settings for business (structured) data execution."""

from __future__ import annotations

import os
from typing import Any

from settings_service import get_raw_settings

DEFAULT_TRINO_HOST = "localhost"
DEFAULT_TRINO_PORT = 8081
DEFAULT_TRINO_USER = "trino"
DEFAULT_TRINO_HTTP_SCHEME = "http"


def get_trino_settings() -> dict[str, Any]:
    """
    Resolve Trino coordinator connection from environment / .env.

  Local Docker: TRINO_HOST=trino, TRINO_PORT=8080
  AWS (future): internal ALB hostname, https + auth via TRINO_PASSWORD or JWT.
    """
    raw = get_raw_settings()
    host = (raw.get("TRINO_HOST") or os.environ.get("TRINO_HOST") or DEFAULT_TRINO_HOST).strip()
    port_raw = (raw.get("TRINO_PORT") or os.environ.get("TRINO_PORT") or str(DEFAULT_TRINO_PORT)).strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = DEFAULT_TRINO_PORT
    user = (raw.get("TRINO_USER") or os.environ.get("TRINO_USER") or DEFAULT_TRINO_USER).strip()
    password = (raw.get("TRINO_PASSWORD") or os.environ.get("TRINO_PASSWORD") or "").strip()
    http_scheme = (
        raw.get("TRINO_HTTP_SCHEME") or os.environ.get("TRINO_HTTP_SCHEME") or DEFAULT_TRINO_HTTP_SCHEME
    ).strip().lower()
    verify_raw = (raw.get("TRINO_VERIFY_SSL") or os.environ.get("TRINO_VERIFY_SSL") or "false").strip().lower()
    verify_ssl = verify_raw in ("1", "true", "yes", "on")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "http_scheme": http_scheme or DEFAULT_TRINO_HTTP_SCHEME,
        "verify_ssl": verify_ssl,
    }


def get_public_trino_settings() -> dict[str, Any]:
    settings = get_trino_settings()
    return {
        "host": settings["host"],
        "port": settings["port"],
        "user": settings["user"],
        "http_scheme": settings["http_scheme"],
        "verify_ssl": settings["verify_ssl"],
        "password_set": bool(settings["password"]),
    }
