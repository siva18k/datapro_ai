"""Saved Trino catalog bindings for business (structured) datasets."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from structured_trino import test_trino_catalog, trino_config_from_connection
from trino_catalog_files import (
    catalog_password_is_set,
    enrich_row_from_catalog_file,
    is_legacy_postgres_row,
    merge_warehouse_credentials,
    normalize_extra,
    suggest_catalog_name,
    trino_binding_from_legacy,
    warehouse_type_label,
    write_warehouse_catalog,
)
from trino_connector_types import (
    default_port_for_type,
    default_schema_for_type,
    list_warehouse_connectors_public,
    normalize_warehouse_type,
    validate_warehouse_row,
)
from structured_db import postgres_config_from_source, test_postgres_connection

PROJECT_DIR = Path(__file__).resolve().parent
CONNECTIONS_PATH = PROJECT_DIR / "saved_db_connections.json"

BUSINESS_CONNECTOR = "trino"
NATIVE_POSTGRES_CONNECTOR = "postgres"
STORED_WAREHOUSE_KEYS = (
    "host",
    "port",
    "user",
    "password",
    "database",
    "warehouse_type",
    "extra",
)


def list_warehouse_connectors() -> list[dict[str, Any]]:
    return list_warehouse_connectors_public()


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


def _migrate_legacy_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map old direct-Postgres saved connections to Trino catalog bindings when possible."""
    connector = (row.get("connector") or "").strip().lower()
    if connector == NATIVE_POSTGRES_CONNECTOR:
        migrated = dict(row)
        migrated["warehouse_type"] = normalize_warehouse_type(migrated.get("warehouse_type") or "postgresql")
        if not migrated.get("extra"):
            migrated["extra"] = normalize_extra(migrated)
        return migrated
    if is_legacy_postgres_row(row):
        return trino_binding_from_legacy(row)
    if connector == BUSINESS_CONNECTOR and row.get("catalog"):
        migrated = dict(row)
        migrated["warehouse_type"] = normalize_warehouse_type(migrated.get("warehouse_type"))
        if not migrated.get("extra"):
            migrated["extra"] = normalize_extra(migrated)
        return enrich_row_from_catalog_file(migrated)
    return row


def _public_connection(row: dict[str, Any]) -> dict[str, Any]:
    row = _migrate_legacy_row(row)
    connector = (row.get("connector") or BUSINESS_CONNECTOR).strip().lower() or BUSINESS_CONNECTOR
    catalog = row.get("catalog") or ""
    warehouse_type = normalize_warehouse_type(row.get("warehouse_type"))
    extra = normalize_extra(row)
    public: dict[str, Any] = {
        "id": row["id"],
        "name": row["name"],
        "connector": connector,
        "warehouse_type": warehouse_type,
        "warehouse_type_label": warehouse_type_label(warehouse_type),
        "catalog": catalog,
        "schema": row.get("schema") or default_schema_for_type(warehouse_type) or "public",
        "host": row.get("host") or "",
        "port": int(row.get("port") or default_port_for_type(warehouse_type)),
        "user": row.get("user") or "",
        "database": row.get("database") or "",
        "password_set": bool(row.get("password")) if connector == NATIVE_POSTGRES_CONNECTOR else catalog_password_is_set(catalog) if catalog else False,
        "extra": extra,
    }
    for key, value in extra.items():
        if key not in public or not str(public.get(key) or "").strip():
            public[key] = value
    if warehouse_type == "postgresql" and extra.get("sslmode"):
        public["sslmode"] = extra["sslmode"]
    elif row.get("sslmode"):
        public["sslmode"] = row["sslmode"]
    return public


def list_connections() -> list[dict[str, Any]]:
    return [_public_connection(row) for row in _load_store()["connections"]]


def get_connection(connection_id: str) -> dict[str, Any] | None:
    for row in _load_store()["connections"]:
        if row.get("id") == connection_id:
            return _migrate_legacy_row(dict(row))
    return None


def get_connection_by_name(name: str) -> dict[str, Any] | None:
    target = (name or "").strip().casefold()
    if not target:
        return None
    for row in _load_store()["connections"]:
        if str(row.get("name") or "").strip().casefold() == target:
            return _migrate_legacy_row(dict(row))
    return None


def resolve_saved_connection(source_or_config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Find the saved connection for a dataset, even if connection_id is stale."""
    cfg = dict((source_or_config or {}).get("config") or source_or_config or {})
    connection_id = str(cfg.get("connection_id") or "").strip()
    if connection_id:
        row = get_connection(connection_id)
        if row:
            return row
    connection_name = str(cfg.get("connection_name") or "").strip()
    if connection_name:
        return get_connection_by_name(connection_name)
    catalog = str(cfg.get("catalog") or "").strip()
    if catalog:
        for row in _load_store()["connections"]:
            if str(row.get("catalog") or "").strip() == catalog:
                return _migrate_legacy_row(dict(row))
    raw = dict(source_or_config or {})
    if raw.get("id") and (raw.get("connector") or "").strip().lower() in {
        BUSINESS_CONNECTOR,
        NATIVE_POSTGRES_CONNECTOR,
    }:
        return _migrate_legacy_row(raw)
    return None


DATASET_LOCAL_CONNECTION_KEYS = frozenset(
    {
        "host",
        "port",
        "user",
        "password",
        "database",
        "sslmode",
        "catalog",
        "trino_catalog",
        "warehouse_type",
        "extra",
    }
)


def bind_source_to_saved_connection(
    source_or_config: dict[str, Any] | None,
    *,
    connection_id: str | None = None,
    schema: str | None = None,
) -> dict[str, Any]:
    """Attach a dataset to a Settings connection. Credentials stay on the connection."""
    cfg = dict((source_or_config or {}).get("config") or source_or_config or {})
    if connection_id:
        cfg["connection_id"] = connection_id
    saved = resolve_saved_connection({"config": cfg})
    if not saved:
        raise ValueError(
            "Choose a connection from Settings. Datasets reuse Settings connections "
            "and do not store their own database credentials."
        )
    connector = (saved.get("connector") or BUSINESS_CONNECTOR).strip().lower() or BUSINESS_CONNECTOR
    schema_name = str(schema or cfg.get("schema") or saved.get("schema") or "public").strip() or "public"
    bound: dict[str, Any] = {
        "connection_id": saved.get("id"),
        "connection_name": saved.get("name") or "",
        "schema": schema_name,
    }
    for key, value in cfg.items():
        if key in DATASET_LOCAL_CONNECTION_KEYS or key in bound:
            continue
        bound[key] = value
    return {"connector": connector, "config": bound}


def connection_config(connection_id: str) -> dict[str, Any]:
    row = get_connection(connection_id)
    if not row:
        raise ValueError("Connection not found")
    schema = (row.get("schema") or "public").strip() or "public"
    connector = (row.get("connector") or "").strip().lower()
    if connector == NATIVE_POSTGRES_CONNECTOR:
        return {
            "connector": NATIVE_POSTGRES_CONNECTOR,
            "host": row.get("host") or "",
            "port": int(row.get("port") or 5432),
            "user": row.get("user") or "",
            "password": row.get("password") or "",
            "database": row.get("database") or "postgres",
            "schema": schema,
            "sslmode": row.get("sslmode") or normalize_extra(row).get("sslmode") or "require",
            "connection_id": connection_id,
            "connection_name": row.get("name", ""),
        }
    catalog = (row.get("catalog") or "").strip()
    if not catalog:
        raise ValueError("Connection is missing Trino catalog name.")
    return {
        "connector": BUSINESS_CONNECTOR,
        "catalog": catalog,
        "schema": schema,
        "warehouse_type": normalize_warehouse_type(row.get("warehouse_type")),
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


def _catalog_taken(catalog: str, *, exclude_id: str | None = None) -> bool:
    target = catalog.strip().casefold()
    if not target:
        return False
    for row in _load_store()["connections"]:
        if exclude_id and row.get("id") == exclude_id:
            continue
        if str(row.get("catalog") or "").strip().casefold() == target:
            return True
    return False


def _validate_catalog_name(catalog: str) -> str:
    value = catalog.strip()
    if not value:
        raise ValueError("Trino catalog name is required.")
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", value):
        raise ValueError(
            "Trino catalog name must start with a letter or underscore and contain only "
            "letters, numbers, and underscores."
        )
    return value


def _store_row_from_payload(payload: dict[str, Any], *, row_id: str | None = None) -> dict[str, Any]:
    name = (payload.get("name") or "").strip()
    connector = (payload.get("connector") or BUSINESS_CONNECTOR).strip().lower() or BUSINESS_CONNECTOR
    warehouse_type = normalize_warehouse_type(payload.get("warehouse_type"))
    catalog = str(payload.get("catalog") or suggest_catalog_name(name)).strip()
    if connector == NATIVE_POSTGRES_CONNECTOR and not catalog:
        catalog = suggest_catalog_name(name)
    if connector == BUSINESS_CONNECTOR:
        catalog = _validate_catalog_name(catalog)
    schema = (payload.get("schema") or default_schema_for_type(warehouse_type)).strip() or "public"
    extra = normalize_extra(payload)
    row: dict[str, Any] = {
        "id": row_id or str(uuid.uuid4()),
        "name": name,
        "connector": connector,
        "warehouse_type": warehouse_type,
        "catalog": catalog,
        "schema": schema,
        "host": (payload.get("host") or "").strip(),
        "port": int(payload.get("port") or default_port_for_type(warehouse_type)),
        "user": (payload.get("user") or "").strip(),
        "password": (payload.get("password") or "").strip() if connector == NATIVE_POSTGRES_CONNECTOR else "",
        "database": (payload.get("database") or "").strip(),
        "extra": extra,
    }
    if warehouse_type == "postgresql" and extra.get("sslmode"):
        row["sslmode"] = extra["sslmode"]
    elif payload.get("sslmode"):
        row["sslmode"] = str(payload["sslmode"]).strip()
    return row


def _apply_catalog_file(row: dict[str, Any], payload: dict[str, Any]) -> None:
    catalog = row["catalog"]
    creds = merge_warehouse_credentials(row, payload, catalog=catalog)
    write_warehouse_catalog(creds, catalog=catalog)


def _credential_fields_in_payload(payload: dict[str, Any]) -> bool:
    keys = (
        "host",
        "user",
        "password",
        "port",
        "database",
        "warehouse_type",
        "extra",
        "sslmode",
        "encrypt",
        "oracle_connect_mode",
        "oracle_service",
        "snowflake_account",
        "snowflake_warehouse",
        "snowflake_role",
        "trino_connector_name",
        "connection_url",
    )
    return any(payload.get(k) for k in keys)


def create_connection(payload: dict[str, Any]) -> dict[str, Any]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("Connection name is required")
    if _name_taken(name):
        raise ValueError(f'Connection name "{name}" is already in use. Choose a unique name.')
    row = _store_row_from_payload({**payload, "name": name})
    if row["connector"] == NATIVE_POSTGRES_CONNECTOR:
        cfg = postgres_config_from_source(row)
        ok, msg = test_postgres_connection({**cfg, "password": row.get("password") or ""})
        if not ok:
            raise ValueError(msg)
    else:
        if not (payload.get("catalog") or "").strip():
            payload = {**payload, "catalog": suggest_catalog_name(name)}
        if _catalog_taken(row["catalog"]):
            raise ValueError(f'Trino catalog "{row["catalog"]}" is already registered. Choose a unique catalog name.')
        creds = merge_warehouse_credentials(row, payload, catalog=row["catalog"])
        validate_warehouse_row(creds, require_password=True)
        _apply_catalog_file(row, payload)
    store = _load_store()
    store["connections"].append(row)
    _save_store(store)
    return _public_connection(row)


def update_connection(connection_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    store = _load_store()
    for row in store["connections"]:
        if row.get("id") != connection_id:
            continue
        row = _migrate_legacy_row(dict(row))
        if payload.get("name") is not None:
            next_name = str(payload["name"]).strip() or row["name"]
            if _name_taken(next_name, exclude_id=connection_id):
                raise ValueError(f'Connection name "{next_name}" is already in use. Choose a unique name.')
            row["name"] = next_name
        target_connector = str(payload.get("connector") or row.get("connector") or BUSINESS_CONNECTOR).strip().lower()
        if payload.get("connector") is not None:
            row["connector"] = target_connector
        if payload.get("warehouse_type") is not None:
            row["warehouse_type"] = normalize_warehouse_type(str(payload["warehouse_type"]))
        if payload.get("catalog") is not None and target_connector != NATIVE_POSTGRES_CONNECTOR:
            next_catalog = _validate_catalog_name(str(payload["catalog"]))
            if _catalog_taken(next_catalog, exclude_id=connection_id):
                raise ValueError(f'Trino catalog "{next_catalog}" is already registered.')
            row["catalog"] = next_catalog
        if payload.get("schema") is not None:
            row["schema"] = str(payload["schema"]).strip() or row.get("schema") or "public"
        for key in STORED_WAREHOUSE_KEYS:
            if payload.get(key) is not None:
                if key == "port":
                    row[key] = int(payload[key] or default_port_for_type(row.get("warehouse_type")))
                elif key == "extra":
                    row[key] = {**normalize_extra(row), **normalize_extra(payload)}
                elif key == "password" and (row.get("connector") or "").strip().lower() != NATIVE_POSTGRES_CONNECTOR:
                    continue
                else:
                    row[key] = payload[key]
        for key in (
            "sslmode",
            "encrypt",
            "oracle_connect_mode",
            "oracle_service",
            "snowflake_account",
            "snowflake_warehouse",
            "snowflake_role",
            "trino_connector_name",
            "connection_url",
        ):
            if payload.get(key) is not None:
                extra = normalize_extra(row)
                extra[key] = str(payload[key]).strip()
                row["extra"] = extra
        if _credential_fields_in_payload(payload) and target_connector == NATIVE_POSTGRES_CONNECTOR:
            cfg = postgres_config_from_source(row)
            ok, msg = test_postgres_connection({**cfg, "password": row.get("password") or ""})
            if not ok:
                raise ValueError(msg)
        elif _credential_fields_in_payload(payload):
            creds = merge_warehouse_credentials(row, payload, catalog=row["catalog"])
            validate_warehouse_row(
                creds,
                require_password=not catalog_password_is_set(row["catalog"]),
            )
            _apply_catalog_file(row, payload)
        for i, stored in enumerate(store["connections"]):
            if stored.get("id") == connection_id:
                store["connections"][i] = row
                break
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
    base = get_connection(connection_id) if connection_id else {}
    base = base or {}
    merged_binding = {
        "catalog": (payload.get("catalog") or base.get("catalog") or "").strip(),
        "schema": (payload.get("schema") or base.get("schema") or "public").strip() or "public",
        "warehouse_type": normalize_warehouse_type(payload.get("warehouse_type") or base.get("warehouse_type")),
    }
    row = _store_row_from_payload({**base, **payload, **merged_binding})
    if row["connector"] == NATIVE_POSTGRES_CONNECTOR:
        cfg = postgres_config_from_source(row)
        ok, message = test_postgres_connection({**cfg, "password": row.get("password") or ""})
        return ok, message

    if not merged_binding["catalog"]:
        if payload.get("name"):
            merged_binding["catalog"] = suggest_catalog_name(str(payload["name"]))
        else:
            raise ValueError("Trino catalog name is required.")

    creds = merge_warehouse_credentials(row, payload, catalog=row["catalog"])
    validate_warehouse_row(
        creds,
        require_password=not catalog_password_is_set(row["catalog"]),
    )
    _apply_catalog_file(row, {**payload, "password": creds.get("password") or ""})
    return test_trino_catalog(trino_config_from_connection(merged_binding))


def migrate_stored_connections(
    *,
    dry_run: bool = False,
    write_catalog: bool = True,
) -> dict[str, Any]:
    """Persist Trino catalog bindings; optionally write Trino catalog property files."""
    store = _load_store()
    changes: list[dict[str, Any]] = []
    catalog_writes: list[str] = []
    migrated: list[dict[str, Any]] = []

    for row in store["connections"]:
        if not is_legacy_postgres_row(row):
            migrated.append(row)
            continue
        binding = trino_binding_from_legacy(row)
        changes.append(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "from": "postgres",
                "catalog": binding["catalog"],
                "schema": binding["schema"],
                "warehouse_type": binding.get("warehouse_type"),
            }
        )
        if write_catalog:
            path = write_warehouse_catalog(row, catalog=binding["catalog"], dry_run=dry_run)
            catalog_writes.append(str(path.relative_to(PROJECT_DIR)))
        migrated.append(binding)

    if not dry_run:
        store["connections"] = migrated
        _save_store(store)

    return {
        "dry_run": dry_run,
        "changed": len(changes),
        "connections": changes,
        "catalog_files": catalog_writes,
    }
