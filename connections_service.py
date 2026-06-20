"""Saved external Postgres connections for dataset creation."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from structured_db import test_postgres_connection

PROJECT_DIR = Path(__file__).resolve().parent
CONNECTIONS_PATH = PROJECT_DIR / "saved_db_connections.json"


def _load_store() -> dict[str, Any]:
    if not CONNECTIONS_PATH.exists():
        return {"connections": []}
    data = json.loads(CONNECTIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data.get("connections"), list):
        return {"connections": []}
    return data


def _save_store(data: dict[str, Any]) -> None:
    CONNECTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONNECTIONS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _public_connection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "host": row.get("host", ""),
        "port": int(row.get("port") or 5432),
        "user": row.get("user", ""),
        "database": row.get("database", ""),
        "schema": row.get("schema") or "public",
        "sslmode": row.get("sslmode") or "require",
        "password_set": bool(row.get("password")),
    }


def list_connections() -> list[dict[str, Any]]:
    return [_public_connection(row) for row in _load_store()["connections"]]


def get_connection(connection_id: str) -> dict[str, Any] | None:
    for row in _load_store()["connections"]:
        if row.get("id") == connection_id:
            return row
    return None


def connection_config(connection_id: str) -> dict[str, Any]:
    row = get_connection(connection_id)
    if not row:
        raise ValueError("Connection not found")
    return {
        "host": row.get("host", ""),
        "port": int(row.get("port") or 5432),
        "user": row.get("user", ""),
        "password": row.get("password", ""),
        "database": row.get("database") or "postgres",
        "schema": row.get("schema") or "public",
        "sslmode": row.get("sslmode") or "require",
        "connection_id": connection_id,
        "connection_name": row.get("name", ""),
    }


def _normalize_name(name: str) -> str:
    return name.strip().casefold()


def _name_taken(name: str, *, exclude_id: str | None = None) -> bool:
    target = _normalize_name(name)
    if not target:
        return False
    for row in _load_store()["connections"]:
        if exclude_id and row.get("id") == exclude_id:
            continue
        if _normalize_name(str(row.get("name") or "")) == target:
            return True
    return False


def create_connection(payload: dict[str, Any]) -> dict[str, Any]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("Connection name is required")
    if _name_taken(name):
        raise ValueError(f'Connection name "{name}" is already in use. Choose a unique name.')
    row = {
        "id": str(uuid.uuid4()),
        "name": name,
        "host": (payload.get("host") or "").strip(),
        "port": int(payload.get("port") or 5432),
        "user": (payload.get("user") or "").strip(),
        "password": payload.get("password") or "",
        "database": (payload.get("database") or "postgres").strip(),
        "schema": (payload.get("schema") or "public").strip() or "public",
        "sslmode": (payload.get("sslmode") or "require").strip() or "require",
    }
    if not all([row["host"], row["user"], row["database"]]):
        raise ValueError("Host, user, and database are required")
    store = _load_store()
    store["connections"].append(row)
    _save_store(store)
    return _public_connection(row)


def update_connection(connection_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    store = _load_store()
    for row in store["connections"]:
        if row.get("id") != connection_id:
            continue
        if payload.get("name") is not None:
            next_name = str(payload["name"]).strip() or row["name"]
            if _name_taken(next_name, exclude_id=connection_id):
                raise ValueError(f'Connection name "{next_name}" is already in use. Choose a unique name.')
            row["name"] = next_name
        for key in ("host", "user", "database", "schema", "sslmode"):
            if payload.get(key) is not None:
                row[key] = str(payload[key]).strip()
        if payload.get("port") is not None:
            row["port"] = int(payload["port"])
        if payload.get("password"):
            row["password"] = str(payload["password"])
        _save_store(store)
        return _public_connection(row)
    raise ValueError("Connection not found")


def delete_connection(connection_id: str) -> None:
    store = _load_store()
    before = len(store["connections"])
    store["connections"] = [r for r in store["connections"] if r.get("id") != connection_id]
    if len(store["connections"]) == before:
        raise ValueError("Connection not found")
    _save_store(store)


def test_connection_payload(payload: dict[str, Any], *, connection_id: str | None = None) -> tuple[bool, str]:
    if connection_id:
        base = get_connection(connection_id) or {}
        config = {
            "host": base.get("host", ""),
            "port": int(base.get("port") or 5432),
            "user": base.get("user", ""),
            "password": base.get("password", ""),
            "database": base.get("database") or "postgres",
            "schema": base.get("schema") or "public",
            "sslmode": base.get("sslmode") or "require",
        }
        if payload.get("host"):
            config["host"] = str(payload["host"]).strip()
        if payload.get("user"):
            config["user"] = str(payload["user"]).strip()
        if payload.get("database"):
            config["database"] = str(payload["database"]).strip()
        if payload.get("port") is not None:
            config["port"] = int(payload["port"])
        if payload.get("schema"):
            config["schema"] = str(payload["schema"]).strip()
        if payload.get("sslmode"):
            config["sslmode"] = str(payload["sslmode"]).strip()
        if payload.get("password"):
            config["password"] = str(payload["password"])
    else:
        config = {
            "host": (payload.get("host") or "").strip(),
            "port": int(payload.get("port") or 5432),
            "user": (payload.get("user") or "").strip(),
            "password": payload.get("password") or "",
            "database": (payload.get("database") or "postgres").strip(),
            "schema": (payload.get("schema") or "public").strip() or "public",
            "sslmode": (payload.get("sslmode") or "require").strip() or "require",
        }
    return test_postgres_connection(config)
