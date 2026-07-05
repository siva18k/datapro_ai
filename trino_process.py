"""Start, stop, and inspect the local Trino coordinator (Podman Compose)."""

from __future__ import annotations

import subprocess
import time
import shutil
from pathlib import Path
from typing import Any

import requests

from mcp_registry import PROJECT_DIR
from trino_settings import get_trino_settings

CONTAINER_NAME = "datapro-trino"
MANAGED_PATH = PROJECT_DIR / ".trino_service.managed"
LOG_PATH = PROJECT_DIR / ".trino_service.log"

STATUS_LABELS = {
    "ui": "Running (started from Settings)",
    "external": "Running (started externally — e.g. podman compose)",
    "unknown": "Running (reachable, container not identified)",
    "stopped": "Stopped",
}


def _trino_info_url(settings: dict[str, Any] | None = None) -> str:
    cfg = settings or get_trino_settings()
    scheme = (cfg.get("http_scheme") or "http").strip().lower()
    host = (cfg.get("host") or "localhost").strip()
    port = int(cfg.get("port") or 8081)
    return f"{scheme}://{host}:{port}/v1/info"


def _trino_base_url(settings: dict[str, Any] | None = None) -> str:
    cfg = settings or get_trino_settings()
    scheme = (cfg.get("http_scheme") or "http").strip().lower()
    host = (cfg.get("host") or "localhost").strip()
    port = int(cfg.get("port") or 8081)
    return f"{scheme}://{host}:{port}"


def check_trino_server(settings: dict[str, Any] | None = None) -> bool:
    try:
        response = requests.get(_trino_info_url(settings), timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _compose_cmd() -> list[str] | None:
    if shutil.which("podman"):
        return ["podman", "compose"]
    if shutil.which("docker"):
        return ["docker", "compose"]
    return None


def docker_available() -> bool:
    return _compose_cmd() is not None


def _docker_compose(args: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    cmd = _compose_cmd()
    if cmd is None:
        raise RuntimeError("Podman or Docker Compose is not available.")
    return subprocess.run(
        [*cmd, *args],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _append_log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def _mark_managed() -> None:
    MANAGED_PATH.write_text(str(int(time.time())), encoding="utf-8")


def _clear_managed() -> None:
    if MANAGED_PATH.exists():
        MANAGED_PATH.unlink()


def _is_managed() -> bool:
    return MANAGED_PATH.exists()


def _container_id() -> str | None:
    if not docker_available():
        return None
    result = _docker_compose(["ps", "-q", "trino"], timeout=30)
    if result.returncode != 0:
        return None
    container_id = (result.stdout or "").strip().splitlines()
    if not container_id:
        return None
    return container_id[0].strip() or None


def get_server_log_tail(max_lines: int = 80) -> str:
    if docker_available():
        result = _docker_compose(["logs", "--tail", str(max_lines), "trino"], timeout=30)
        if result.stdout.strip():
            return result.stdout.strip()
        if result.stderr.strip():
            return result.stderr.strip()
    if LOG_PATH.exists():
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    return ""


def get_server_status(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = settings or get_trino_settings()
    url = _trino_base_url(cfg)
    info_url = _trino_info_url(cfg)
    port = int(cfg.get("port") or 8081)
    host = (cfg.get("host") or "localhost").strip()
    reachable = check_trino_server(cfg)
    container_id = _container_id()
    container_running = bool(container_id)

    if reachable:
        if container_running and _is_managed():
            source = "ui"
        elif container_running:
            source = "external"
        else:
            source = "unknown"
    else:
        source = "stopped"

    return {
        "url": url,
        "info_url": info_url,
        "host": host,
        "port": port,
        "reachable": reachable,
        "running": reachable or container_running,
        "container_running": container_running,
        "source": source,
        "status_label": STATUS_LABELS[source],
        "container_id": container_id,
        "container_name": CONTAINER_NAME,
        "docker_available": docker_available(),
        "log_path": str(LOG_PATH),
        "managed": _is_managed(),
    }


def start_server(settings: dict[str, Any] | None = None) -> tuple[bool, str]:
    cfg = settings or get_trino_settings()
    url = _trino_base_url(cfg)
    status = get_server_status(cfg)
    if status["reachable"]:
        if status["source"] == "external":
            return False, (
                f"Trino is already reachable at {url} (external container). "
                "Use **Stop** first if you want to restart from Settings."
            )
        return False, f"Trino coordinator is already reachable at {url}"

    if not docker_available():
        return False, (
            "Podman or Docker Compose is not available. Start Podman or Docker, then try again. "
            "Local dev: `podman compose up -d trino` from the project root."
        )

    _append_log("podman compose up -d trino")
    result = _docker_compose(["up", "-d", "trino"])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "podman compose failed").strip()
        _append_log(f"start failed: {detail}")
        return False, detail

    for _ in range(60):
        time.sleep(1)
        if check_trino_server(cfg):
            _mark_managed()
            _append_log(f"started — reachable at {url}")
            return True, f"Started Trino coordinator at {url}"
        if _container_id() is None:
            tail = get_server_log_tail(15)
            _append_log("container exited during startup")
            return False, f"Trino container stopped during startup.\n{tail}"

    tail = get_server_log_tail(15)
    return False, (
        f"Trino container started but {url} is not reachable yet. "
        f"Confirm TRINO_HOST/TRINO_PORT in Settings (use localhost:8081 from the host).\n{tail}"
    )


def stop_server(settings: dict[str, Any] | None = None) -> tuple[bool, str]:
    cfg = settings or get_trino_settings()
    url = _trino_base_url(cfg)
    status = get_server_status(cfg)

    if not status["container_running"] and not status["reachable"]:
        return False, "Trino coordinator is not running."

    if not docker_available():
        return False, "Podman or Docker Compose is not available — cannot stop the Trino container."

    _append_log("podman compose stop trino")
    result = _docker_compose(["stop", "trino"], timeout=120)
    _clear_managed()
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "podman compose stop failed").strip()
        _append_log(f"stop failed: {detail}")
        return False, detail

    if check_trino_server(cfg):
        return False, f"Stop command ran but Trino is still reachable at {url}."

    return True, "Stopped Trino coordinator."


def restart_server(settings: dict[str, Any] | None = None) -> tuple[bool, str]:
    cfg = settings or get_trino_settings()
    url = _trino_base_url(cfg)

    if not docker_available():
        return False, "Podman or Docker Compose is not available. Start Podman or Docker, then try again."

    if not _container_id():
        return start_server(cfg)

    _append_log("podman compose restart trino")
    result = _docker_compose(["restart", "trino"], timeout=120)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "podman compose restart failed").strip()
        _append_log(f"restart failed: {detail}")
        return False, detail

    for _ in range(60):
        time.sleep(1)
        if check_trino_server(cfg):
            _mark_managed()
            _append_log(f"restarted — reachable at {url}")
            return True, f"Restarted Trino coordinator at {url}"

    tail = get_server_log_tail(15)
    return False, f"Trino restarted but {url} is not reachable yet.\n{tail}"
