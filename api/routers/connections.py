from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from connections_service import (
    connection_config,
    create_connection,
    delete_connection,
    list_connections,
    list_warehouse_connectors,
    test_connection_payload,
    update_connection,
)
from trino_settings import get_public_trino_settings
from structured_trino import test_trino_catalog, test_trino_server as ping_trino_server
from trino_settings import get_trino_settings

router = APIRouter(prefix="/connections", tags=["connections"])


class DbConnectionBody(BaseModel):
    name: str = ""
    connector: str = Field(default="trino")
    warehouse_type: str = Field(default="postgresql")
    catalog: str = ""
    schema: str = "public"
    host: str = ""
    port: int = 5432
    user: str = ""
    password: str = ""
    database: str = ""
    sslmode: str = "require"
    encrypt: str = ""
    oracle_connect_mode: str = ""
    oracle_service: str = ""
    snowflake_account: str = ""
    snowflake_warehouse: str = ""
    snowflake_role: str = ""
    trino_connector_name: str = ""
    connection_url: str = ""
    extra: dict[str, str] | None = None


class DbConnectionCreate(DbConnectionBody):
    name: str


class DbConnectionUpdate(BaseModel):
    name: str | None = None
    connector: str | None = None
    warehouse_type: str | None = None
    catalog: str | None = None
    schema: str | None = None
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    database: str | None = None
    sslmode: str | None = None
    encrypt: str | None = None
    oracle_connect_mode: str | None = None
    oracle_service: str | None = None
    snowflake_account: str | None = None
    snowflake_warehouse: str | None = None
    snowflake_role: str | None = None
    trino_connector_name: str | None = None
    connection_url: str | None = None
    extra: dict[str, str] | None = None


class TrinoSettingsBody(BaseModel):
    host: str = ""
    port: int = 8081
    user: str = "trino"
    password: str = ""
    http_scheme: str = "http"
    verify_ssl: bool = False


@router.get("")
def list_saved():
    return list_connections()


@router.get("/warehouse-connectors")
def warehouse_connectors():
    return list_warehouse_connectors()


@router.get("/trino-settings")
def trino_settings():
    return get_public_trino_settings()


@router.post("/trino-settings/test")
def test_trino_coordinator(body: TrinoSettingsBody | None = None):
    base = get_trino_settings()
    if body:
        provided = set(getattr(body, "model_fields_set", set()))
        if "host" in provided and body.host.strip():
            base["host"] = body.host.strip()
        if "port" in provided:
            base["port"] = int(body.port)
        if "user" in provided and body.user.strip():
            base["user"] = body.user.strip()
        if "password" in provided and body.password:
            base["password"] = body.password
        if "http_scheme" in provided:
            base["http_scheme"] = (body.http_scheme or "http").strip().lower()
        if "verify_ssl" in provided:
            base["verify_ssl"] = bool(body.verify_ssl)
    ok, message = ping_trino_server(base)
    if not ok:
        raise HTTPException(400, message)
    return {"ok": True, "message": message or "Trino coordinator is reachable."}


@router.get("/{connection_id}/config")
def get_config(connection_id: str):
    try:
        return connection_config(connection_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("", status_code=201)
def create(body: DbConnectionCreate):
    try:
        return create_connection(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/{connection_id}")
def patch(connection_id: str, body: DbConnectionUpdate):
    try:
        return update_connection(connection_id, body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{connection_id}")
def remove(connection_id: str):
    try:
        delete_connection(connection_id)
        return {"deleted": True}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/test")
def test_new(body: DbConnectionBody):
    ok, message = test_connection_payload(body.model_dump())
    if not ok:
        raise HTTPException(400, message)
    return {"ok": True, "message": message}


@router.post("/{connection_id}/test")
def test_saved(connection_id: str, body: DbConnectionBody | None = None):
    ok, message = test_connection_payload(
        (body.model_dump() if body else {}),
        connection_id=connection_id,
    )
    if not ok:
        raise HTTPException(400, message)
    return {"ok": True, "message": message}
