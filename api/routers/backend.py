from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Query

from api_process import (
    get_server_log_tail,
    get_server_status,
    restart_server,
    run_stop_server_subprocess,
    start_server,
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
    status = _status_payload()
    if not status["reachable"] and not status["listener_pids"]:
        return {
            "ok": False,
            "message": "No API server is running on the configured port.",
            **status,
        }

    def _stop_in_subprocess() -> None:
        run_stop_server_subprocess(
            host=status.get("host"),
            port=status.get("port"),
        )

    if would_stop_current_process(status.get("port")):
        background_tasks.add_task(_stop_in_subprocess)
        return {
            "ok": True,
            "message": (
                f"Stopping API server at {status['url']}. "
                "This page will lose connection until you start the server again."
            ),
            **status,
        }

    ok, message = run_stop_server_subprocess(
        host=status.get("host"),
        port=status.get("port"),
    )
    return {"ok": ok, "message": message, **_status_payload()}


@router.post("/restart")
def backend_restart():
    ok, message = restart_server()
    return {"ok": ok, "message": message, **_status_payload()}


@router.get("/log")
def backend_log(lines: int = Query(default=80, ge=1, le=500)):
    return {"log": get_server_log_tail(max_lines=lines)}
