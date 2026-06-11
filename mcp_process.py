"""Start, stop, and inspect the local MCP server process."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from mcp_client import check_mcp_server
from mcp_registry import PROJECT_DIR, build_mcp_url, load_registry

PID_PATH = PROJECT_DIR / ".mcp_server.pid"
LOG_PATH = PROJECT_DIR / ".mcp_server.log"

STATUS_LABELS = {
    "ui": "Running (started from this app)",
    "external": "Running (started externally — e.g. terminal)",
    "unknown": "Running (reachable, process not identified on port)",
    "stopped": "Stopped",
}


def _read_pid() -> int | None:
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    PID_PATH.write_text(str(pid), encoding="utf-8")


def _clear_pid() -> None:
    if PID_PATH.exists():
        PID_PATH.unlink()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _get_process_command(pid: int) -> str:
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


def _is_mcp_server_process(pid: int) -> bool:
    command = _get_process_command(pid)
    return "mcp_server" in command


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


def find_mcp_server_pids(registry: dict | None = None) -> list[int]:
    """Return PIDs listening on the configured port that look like mcp_server.py."""
    registry = registry or load_registry()
    port = int(registry["server"].get("port", 8000))
    return [pid for pid in _find_listener_pids(port) if _is_mcp_server_process(pid)]


def _terminate_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError as exc:
        raise RuntimeError(f"No permission to stop pid {pid}: {exc}") from exc

    for _ in range(20):
        time.sleep(0.25)
        if not _pid_alive(pid):
            return

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def get_server_log_tail(max_lines: int = 80) -> str:
    if not LOG_PATH.exists():
        return ""
    lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def get_server_status(registry: dict | None = None) -> dict:
    registry = registry or load_registry()
    url = build_mcp_url(registry)
    port = int(registry["server"].get("port", 8000))
    reachable = check_mcp_server(url)

    managed_pid = _read_pid()
    managed_alive = bool(managed_pid and _pid_alive(managed_pid))
    listener_pids = find_mcp_server_pids(registry)

    if reachable:
        if managed_alive and managed_pid in listener_pids:
            source = "ui"
            active_pid = managed_pid
        elif listener_pids:
            source = "external"
            active_pid = listener_pids[0]
        else:
            source = "unknown"
            active_pid = managed_pid if managed_alive else None
    else:
        source = "stopped"
        active_pid = None

    port_in_use_by_other = False
    if listener_pids and not reachable:
        port_in_use_by_other = True
    all_port_pids = _find_listener_pids(port)
    if reachable and not listener_pids and all_port_pids:
        port_in_use_by_other = True

    return {
        "url": url,
        "port": port,
        "reachable": reachable,
        "running": reachable,
        "source": source,
        "status_label": STATUS_LABELS[source],
        "active_pid": active_pid,
        "listener_pids": listener_pids,
        "managed_pid": managed_pid if managed_alive else None,
        "pid": active_pid,
        "pid_alive": bool(active_pid and _pid_alive(active_pid)),
        "log_path": str(LOG_PATH),
        "port_in_use_by_other": port_in_use_by_other,
    }


def start_server(registry: dict | None = None) -> tuple[bool, str]:
    registry = registry or load_registry()
    url = build_mcp_url(registry)
    status = get_server_status(registry)
    if status["reachable"]:
        if status["source"] == "external":
            return False, (
                f"MCP server already running externally (pid {status['active_pid']}) at {url}. "
                "Use **Stop server** first if you want to restart from this app."
            )
        return False, f"MCP server already reachable at {url}"

    port = int(registry["server"].get("port", 8000))
    blocking = [pid for pid in _find_listener_pids(port) if pid not in status["listener_pids"]]
    if blocking:
        return False, (
            f"Port {port} is already in use by pid {blocking[0]}. "
            "Stop that process before starting the MCP server."
        )

    server = registry["server"]
    env = os.environ.copy()
    env["MCP_HOST"] = str(server.get("host", "0.0.0.0"))
    env["MCP_PORT"] = str(server.get("port", 8000))
    env["MCP_PATH"] = str(server.get("path", "/mcp"))
    env["MCP_TRANSPORT"] = str(server.get("transport", "streamable-http"))
    env["MCP_STATELESS"] = "true" if server.get("stateless", True) else "false"

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_PATH.open("a", encoding="utf-8")
    log_handle.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_handle.flush()

    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_DIR / "mcp_server.py")],
        cwd=str(PROJECT_DIR),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _write_pid(proc.pid)

    for _ in range(30):
        time.sleep(0.5)
        if check_mcp_server(url):
            return True, f"Started MCP server (pid {proc.pid}) at {url}"
        if proc.poll() is not None:
            _clear_pid()
            tail = get_server_log_tail(20)
            return False, f"Server exited early (code {proc.returncode}).\n{tail}"

    return False, (
        f"Process started (pid {proc.pid}) but {url} is not reachable yet. "
        "Check the server log below."
    )


def stop_server(registry: dict | None = None) -> tuple[bool, str]:
    registry = registry or load_registry()
    url = build_mcp_url(registry)
    pids = find_mcp_server_pids(registry)

    if not pids:
        _clear_pid()
        if check_mcp_server(url):
            return False, (
                f"Server is still reachable at {url}, but its process could not be found on "
                f"port {registry['server'].get('port', 8000)}. Stop it manually in your terminal."
            )
        return False, "No MCP server is running on the configured port."

    stopped: list[int] = []
    errors: list[str] = []
    for pid in pids:
        try:
            _terminate_pid(pid)
            stopped.append(pid)
        except RuntimeError as exc:
            errors.append(str(exc))

    _clear_pid()
    time.sleep(0.5)

    if check_mcp_server(url):
        remaining = find_mcp_server_pids(registry)
        if remaining:
            return False, (
                f"Sent stop signal to pid(s) {stopped}, but server is still running "
                f"(pid(s) {remaining}). Stop manually in your terminal."
            )
        return False, f"Stop signal sent, but {url} is still reachable."

    if errors:
        return False, "\n".join(errors)

    label = ", ".join(str(pid) for pid in stopped)
    return True, f"Stopped MCP server (pid {label})."


def restart_server(registry: dict | None = None) -> tuple[bool, str]:
    registry = registry or load_registry()
    status = get_server_status(registry)
    stop_msg = "Server was not running."

    if status["reachable"] or status["listener_pids"]:
        stop_ok, stop_msg = stop_server(registry)
        if not stop_ok and get_server_status(registry)["reachable"]:
            return False, stop_msg
        time.sleep(0.5)

    start_ok, start_msg = start_server(registry)
    if start_ok:
        if status["reachable"] or status["listener_pids"]:
            return True, f"{stop_msg}\n{start_msg}"
        return True, start_msg
    return False, start_msg
