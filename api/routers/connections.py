from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from connections_service import (
    connection_config,
    create_connection,
    delete_connection,
    list_connections,
    test_connection_payload,
    update_connection,
)

router = APIRouter(prefix="/connections", tags=["connections"])


class DbConnectionBody(BaseModel):
    name: str = ""
    host: str = ""
    port: int = 5432
    user: str = ""
    password: str = ""
    database: str = "postgres"
    schema: str = "public"
    sslmode: str = "require"


class DbConnectionCreate(DbConnectionBody):
    name: str


class DbConnectionUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    database: str | None = None
    schema: str | None = None
    sslmode: str | None = None


@router.get("")
def list_saved():
    return list_connections()


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
