"""Start, stop, and inspect optional MCP integrations (email)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mcp_client import check_mcp_server, invalidate_mcp_reachability_cache
from mcp_registry import PROJECT_DIR

MANAGED_INTEGRATIONS: dict[str, dict[str, Any]] = {
    "email_smtp": {
        "runtime": "process",
        "script": "email_mcp_server.py",
        "process_match": "email_mcp_server",
        "port": 8010,
        "pid_path": PROJECT_DIR / ".email_mcp.pid",
        "log_path": PROJECT_DIR / ".email_mcp.log",
    },
}


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _find_listener_pids(port: int) -> list[int]:
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [int(token) for token in result.stdout.split() if token.strip().isdigit()]
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []


def _process_command(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _terminate_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(20):
        time.sleep(0.25)
        if not _pid_alive(pid):
            return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _write_pid(path: Path, pid: int) -> None:
    path.write_text(str(pid), encoding="utf-8")


def _clear_pid(path: Path) -> None:
    if path.exists():
        path.unlink()


def _log_tail(path: Path, max_lines: int = 15) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def _find_process_pids(spec: dict) -> list[int]:
    match = spec["process_match"]
    port = int(spec["port"])
    return [pid for pid in _find_listener_pids(port) if match in _process_command(pid)]


def get_integration_status(slug: str, *, url: str) -> dict[str, Any]:
    spec = MANAGED_INTEGRATIONS.get(slug)
    if not spec:
        return {
            "can_manage": False,
            "reachable": check_mcp_server(url),
            "running": check_mcp_server(url),
            "status_label": "External",
        }

    port = int(spec["port"])
    mcp_reachable = check_mcp_server(url)
    pid_path: Path = spec["pid_path"]
    managed_pid = _read_pid(pid_path)
    listener_pids = _find_process_pids(spec)
    running = bool(listener_pids) or bool(managed_pid and _pid_alive(managed_pid))
    if mcp_reachable:
        status_label = "Reachable"
    elif running:
        status_label = "Starting…"
    else:
        status_label = "Stopped"
    return {
        "can_manage": True,
        "runtime": spec["runtime"],
        "reachable": mcp_reachable,
        "running": running,
        "status_label": status_label,
        "port": port,
        "active_pid": listener_pids[0] if listener_pids else managed_pid,
        "log_path": str(spec["log_path"]),
    }


def enrich_server_runtime(server: dict) -> dict:
    if server.get("is_builtin"):
        from mcp_process import get_server_status

        status = get_server_status()
        return {
            **server,
            "can_manage": True,
            "reachable": status["reachable"],
            "running": status["running"],
            "status_label": status["status_label"],
            "runtime": "process",
            "port": status["port"],
        }
    slug = server.get("slug") or ""
    url = server.get("url") or ""
    runtime = get_integration_status(slug, url=url)
    return {**server, **runtime}


def start_integration(slug: str, *, url: str) -> tuple[bool, str]:
    spec = MANAGED_INTEGRATIONS.get(slug)
    if not spec:
        return False, "This MCP server cannot be started from the app."

    status = get_integration_status(slug, url=url)
    if status.get("reachable"):
        return False, f"{slug} is already reachable at {url}"

    return _start_process_integration(slug, spec, url)


def stop_integration(slug: str, *, url: str) -> tuple[bool, str]:
    spec = MANAGED_INTEGRATIONS.get(slug)
    if not spec:
        return False, "This MCP server cannot be stopped from the app."
    return _stop_process_integration(slug, spec, url)


def _start_process_integration(slug: str, spec: dict, url: str) -> tuple[bool, str]:
    port = int(spec["port"])
    pid_path: Path = spec["pid_path"]
    log_path: Path = spec["log_path"]
    script = PROJECT_DIR / spec["script"]

    blocking = [pid for pid in _find_listener_pids(port) if pid not in _find_process_pids(spec)]
    if blocking:
        return False, f"Port {port} is in use by pid {blocking[0]}. Stop that process first."

    env = os.environ.copy()
    env.setdefault("EMAIL_MCP_HOST", "0.0.0.0")
    env.setdefault("EMAIL_MCP_PORT", str(port))
    env.setdefault("EMAIL_MCP_PATH", "/mcp")
    env.setdefault("EMAIL_MCP_TRANSPORT", "streamable-http")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    log_handle.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_handle.flush()

    proc = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=str(PROJECT_DIR),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _write_pid(pid_path, proc.pid)
    invalidate_mcp_reachability_cache(url)

    for _ in range(40):
        time.sleep(0.5)
        if check_mcp_server(url, use_cache=False, timeout=1):
            invalidate_mcp_reachability_cache(url)
            return True, f"Started {slug} (pid {proc.pid}) at {url}"
        if proc.poll() is not None:
            _clear_pid(pid_path)
            tail = _log_tail(log_path)
            return False, f"Server exited early (code {proc.returncode}).\n{tail}"

    return False, (
        f"Process started (pid {proc.pid}) but {url} is not reachable yet. "
        "Check SMTP_* settings in .env and the log file."
    )


def _stop_process_integration(slug: str, spec: dict, url: str) -> tuple[bool, str]:
    pid_path: Path = spec["pid_path"]
    pids = _find_process_pids(spec)
    if not pids:
        _clear_pid(pid_path)
        if check_mcp_server(url):
            return False, f"{slug} is still reachable at {url} but its process was not found on port {spec['port']}."
        return False, f"{slug} is not running."

    stopped = []
    for pid in pids:
        _terminate_pid(pid)
        stopped.append(pid)
    _clear_pid(pid_path)
    time.sleep(0.5)

    if check_mcp_server(url):
        return False, f"Stop signal sent, but {url} is still reachable."

    return True, f"Stopped {slug} (pid {', '.join(str(p) for p in stopped)})."
