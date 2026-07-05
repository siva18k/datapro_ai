"""Write and read Trino catalog property files for warehouse connections."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from trino_connector_types import (
    build_catalog_properties,
    default_port_for_type,
    default_schema_for_type,
    extract_row_extras_from_catalog,
    infer_warehouse_type_from_catalog_file,
    normalize_warehouse_type,
    parse_catalog_properties,
    warehouse_connector_label,
)

PROJECT_DIR = Path(__file__).resolve().parent
TRINO_CATALOG_DIR = PROJECT_DIR / "docker" / "trino" / "catalog"

EXTRA_PAYLOAD_KEYS = (
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


def catalog_properties_path(catalog: str) -> Path:
    return TRINO_CATALOG_DIR / f"{catalog}.properties"


def catalog_example_path(catalog: str) -> Path:
    return TRINO_CATALOG_DIR / f"{catalog}.properties.example"


def suggest_catalog_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    if not slug:
        return "warehouse"
    if slug[0].isdigit():
        slug = f"c_{slug}"
    return slug


def is_legacy_postgres_row(row: dict[str, Any]) -> bool:
    connector = (row.get("connector") or "").strip().lower()
    has_host = bool((row.get("host") or "").strip())
    if connector == "trino" and row.get("catalog"):
        return False
    return has_host and connector in ("", "postgres")


def infer_trino_catalog_schema(row: dict[str, Any]) -> tuple[str, str]:
    name = (row.get("name") or "").strip()
    schema = (row.get("schema") or default_schema_for_type(row.get("warehouse_type", "postgresql"))).strip()
    if row.get("catalog"):
        return str(row["catalog"]).strip(), schema or "public"
    if schema.casefold() == "finance_data" or re.search(r"finance", name, re.I):
        return "finance", schema if schema else "finance_data"
    return suggest_catalog_name(name), schema or "public"


def normalize_extra(payload: dict[str, Any]) -> dict[str, str]:
    extra: dict[str, str] = {}
    raw = payload.get("extra")
    if isinstance(raw, dict):
        extra.update({str(k): str(v) for k, v in raw.items() if v is not None and str(v).strip()})
    for key in EXTRA_PAYLOAD_KEYS:
        if payload.get(key) is not None and str(payload[key]).strip():
            extra[key] = str(payload[key]).strip()
    return extra


def row_with_extra(row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(row)
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    for key, value in extra.items():
        if key not in merged or not str(merged.get(key) or "").strip():
            merged[key] = value
    return merged


def read_catalog_file(catalog: str) -> dict[str, str]:
    path = catalog_properties_path(catalog)
    if not path.exists():
        return {}
    return parse_catalog_properties(path.read_text(encoding="utf-8"))


def read_catalog_password(catalog: str) -> str:
    return read_catalog_file(catalog).get("connection-password", "")


def catalog_password_is_set(catalog: str) -> bool:
    return bool(read_catalog_password(catalog))


def enrich_row_from_catalog_file(row: dict[str, Any]) -> dict[str, Any]:
    """Fill warehouse_type/extra from catalog file when JSON row is incomplete."""
    catalog = (row.get("catalog") or "").strip()
    if not catalog:
        return row
    props = read_catalog_file(catalog)
    if not props:
        return row
    enriched = dict(row)
    if not enriched.get("warehouse_type"):
        enriched["warehouse_type"] = infer_warehouse_type_from_catalog_file(props)
    url = props.get("connection-url") or ""
    if not enriched.get("host"):
        m = re.search(r"://([^:/]+)", url)
        if m:
            enriched["host"] = m.group(1)
    if not enriched.get("port"):
        m = re.search(r":(\d+)", url)
        if m:
            enriched["port"] = int(m.group(1))
        else:
            enriched["port"] = default_port_for_type(enriched.get("warehouse_type", "postgresql"))
    if not enriched.get("user") and props.get("connection-user"):
        enriched["user"] = props["connection-user"]
    extra = normalize_extra(enriched)
    extra.update(extract_row_extras_from_catalog(props, enriched.get("warehouse_type", "postgresql")))
    enriched["extra"] = extra
    return enriched


def ensure_catalog_example(catalog: str) -> None:
    example = catalog_example_path(catalog)
    target = catalog_properties_path(catalog)
    if target.exists() or not example.exists():
        return
    TRINO_CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example, target)


def write_warehouse_catalog(
    row: dict[str, Any],
    *,
    catalog: str | None = None,
    dry_run: bool = False,
) -> Path:
    catalog_name = (catalog or row.get("catalog") or suggest_catalog_name(row.get("name", ""))).strip()
    if not catalog_name:
        raise ValueError("Trino catalog name is required.")
    ensure_catalog_example(catalog_name)
    path = catalog_properties_path(catalog_name)
    content = build_catalog_properties(row_with_extra({**row, "catalog": catalog_name}), catalog=catalog_name)
    if dry_run:
        return path
    TRINO_CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


write_postgres_catalog = write_warehouse_catalog


def write_postgres_catalog_from_legacy(
    row: dict[str, Any],
    *,
    catalog: str | None = None,
    dry_run: bool = False,
) -> Path:
    legacy = {**row, "warehouse_type": normalize_warehouse_type(row.get("warehouse_type") or "postgresql")}
    return write_warehouse_catalog(legacy, catalog=catalog, dry_run=dry_run)


def trino_binding_from_legacy(row: dict[str, Any]) -> dict[str, Any]:
    catalog, schema = infer_trino_catalog_schema(row)
    binding = {
        "id": row["id"],
        "name": row.get("name") or catalog,
        "connector": "trino",
        "warehouse_type": normalize_warehouse_type(row.get("warehouse_type") or "postgresql"),
        "catalog": catalog,
        "schema": schema,
        "host": row.get("host") or "",
        "port": int(row.get("port") or default_port_for_type("postgresql")),
        "user": row.get("user") or "",
        "database": row.get("database") or "postgres",
        "extra": normalize_extra(row),
    }
    return binding


def merge_warehouse_credentials(
    base: dict[str, Any],
    payload: dict[str, Any],
    *,
    catalog: str,
) -> dict[str, Any]:
    merged = {**base, **{k: v for k, v in payload.items() if v is not None and v != ""}}
    merged["extra"] = {**normalize_extra(base), **normalize_extra(payload)}
    password = (payload.get("password") or "").strip()
    if not password:
        password = read_catalog_password(catalog)
    merged["password"] = password
    merged["warehouse_type"] = normalize_warehouse_type(
        merged.get("warehouse_type") or payload.get("warehouse_type") or base.get("warehouse_type")
    )
    return row_with_extra(merged)


def warehouse_type_label(warehouse_type: str) -> str:
    return warehouse_connector_label(warehouse_type)
