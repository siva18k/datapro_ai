from __future__ import annotations

from fastapi import APIRouter, Query

from trino_process import (
    get_server_log_tail,
    get_server_status,
    restart_server,
    start_server,
    stop_server,
)

router = APIRouter(prefix="/trino-service", tags=["trino-service"])


def _status_payload() -> dict:
    return get_server_status()


@router.get("/status")
def trino_service_status():
    return _status_payload()


@router.post("/start")
def trino_service_start():
    ok, message = start_server()
    return {"ok": ok, "message": message, **_status_payload()}


@router.post("/stop")
def trino_service_stop():
    ok, message = stop_server()
    return {"ok": ok, "message": message, **_status_payload()}


@router.post("/restart")
def trino_service_restart():
    ok, message = restart_server()
    return {"ok": ok, "message": message, **_status_payload()}


@router.get("/log")
def trino_service_log(lines: int = Query(default=80, ge=1, le=500)):
    return {"log": get_server_log_tail(max_lines=lines)}
