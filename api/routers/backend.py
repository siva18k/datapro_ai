from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Query

from api_process import (
    delayed_stop,
    get_server_log_tail,
    get_server_status,
    restart_server,
    start_server,
    stop_server,
    would_stop_current_process,
)

router = APIRouter(prefix="/backend", tags=["backend"])


def _status_payload() -> dict:
    return get_server_status()


@router.get("/status")
def backend_status():
    return _status_payload()


@router.post("/start")
def backend_start():
    ok, message = start_server()
    return {"ok": ok, "message": message, **_status_payload()}


@router.post("/stop")
def backend_stop(background_tasks: BackgroundTasks):
    if would_stop_current_process():
        background_tasks.add_task(delayed_stop)
        status = _status_payload()
        return {
            "ok": True,
            "message": (
                f"Stopping API server at {status['url']}. "
                "This page will lose connection until you start the server again."
            ),
            **status,
        }
    ok, message = stop_server()
    return {"ok": ok, "message": message, **_status_payload()}


@router.post("/restart")
def backend_restart():
    ok, message = restart_server()
    return {"ok": ok, "message": message, **_status_payload()}


@router.get("/log")
def backend_log(lines: int = Query(default=80, ge=1, le=500)):
    return {"log": get_server_log_tail(max_lines=lines)}
