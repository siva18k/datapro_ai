"""Start, stop, and inspect the local FastAPI (uvicorn) server process."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from mcp_registry import PROJECT_DIR
from settings_service import apply_managed_settings_to_env

PID_PATH = PROJECT_DIR / ".api_server.pid"
LOG_PATH = PROJECT_DIR / ".api_server.log"
RESTARTER_PATH = PROJECT_DIR / "scripts" / "api_restarter.py"

DEFAULT_HOST = os.environ.get("API_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("API_PORT", "8080"))

STATUS_LABELS = {
    "ui": "Running (started from this app)",
    "external": "Running (started externally — e.g. terminal)",
    "current": "Running (serving this request)",
    "unknown": "Running (reachable, process not identified on port)",
    "stopped": "Stopped",
}


def build_api_url(*, host: str | None = None, port: int | None = None) -> str:
    host = host or DEFAULT_HOST
    port = port if port is not None else DEFAULT_PORT
    return f"http://{host}:{port}"


def build_health_url(*, host: str | None = None, port: int | None = None) -> str:
    return f"{build_api_url(host=host, port=port)}/api/health"


def check_api_server(url: str | None = None) -> bool:
    health_url = url or build_health_url()
    try:
        response = requests.get(health_url, timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False


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


def _get_ppid(pid: int) -> int | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "ppid="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        text = result.stdout.strip()
        return int(text) if text.isdigit() else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _process_chain(pid: int, *, max_depth: int = 10) -> list[int]:
    chain = [pid]
    current = pid
    for _ in range(max_depth):
        ppid = _get_ppid(current)
        if ppid is None or ppid <= 1:
            break
        chain.append(ppid)
        current = ppid
    return chain


def _listener_serves_datapro_api(port: int) -> bool:
    """True when something on this port responds like the DATA Pro FastAPI app."""
    try:
        health = requests.get(build_health_url(port=port), timeout=2)
        if health.status_code != 200:
            return False
        openapi = requests.get(f"{build_api_url(port=port)}/openapi.json", timeout=2)
        return openapi.status_code == 200 and "DATA Pro API" in openapi.text
    except requests.RequestException:
        return False


def _is_api_server_process(pid: int, *, port: int | None = None) -> bool:
    port = port if port is not None else DEFAULT_PORT
    command = _get_process_command(pid)
    if "uvicorn" in command and "api.main" in command:
        return True
    if "multiprocessing.spawn" in command and "spawn_main" in command:
        for ancestor in _process_chain(pid)[1:]:
            anc_cmd = _get_process_command(ancestor)
            if "uvicorn" in anc_cmd and "api.main" in anc_cmd:
                return True
        # Orphaned uvicorn --reload worker (parent exited)
        return _listener_serves_datapro_api(port)
    return False


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


def find_api_server_pids(port: int | None = None) -> list[int]:
    port = port if port is not None else DEFAULT_PORT
    listeners = _find_listener_pids(port)
    if not listeners:
        return []
    pids = [pid for pid in listeners if _is_api_server_process(pid, port=port)]
    if pids:
        return pids
    if _listener_serves_datapro_api(port):
        return listeners
    return []


def _current_process_pids() -> set[int]:
    pids = {os.getpid()}
    try:
        pids.add(os.getppid())
    except OSError:
        pass
    return pids


def would_stop_current_process(port: int | None = None) -> bool:
    port = port if port is not None else DEFAULT_PORT
    current = _current_process_pids()
    return any(pid in current for pid in find_api_server_pids(port))


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


def _stop_pids(pids: list[int]) -> tuple[list[int], list[str]]:
    """Stop API listener pid(s) and any uvicorn parent in the same chain."""
    targets: set[int] = set()
    for pid in pids:
        targets.add(pid)
        for ancestor in _process_chain(pid):
            cmd = _get_process_command(ancestor)
            if "uvicorn" in cmd and "api.main" in cmd:
                targets.add(ancestor)
                break

    stopped: list[int] = []
    errors: list[str] = []
    for pid in sorted(targets, reverse=True):
        try:
            _terminate_pid(pid)
            stopped.append(pid)
        except RuntimeError as exc:
            errors.append(str(exc))
    return stopped, errors


def get_server_log_tail(max_lines: int = 80) -> str:
    if not LOG_PATH.exists():
        return ""
    lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def get_server_status(*, host: str | None = None, port: int | None = None) -> dict:
    host = host or DEFAULT_HOST
    port = port if port is not None else DEFAULT_PORT
    url = build_api_url(host=host, port=port)
    health_url = build_health_url(host=host, port=port)
    reachable = check_api_server(health_url)

    managed_pid = _read_pid()
    managed_alive = bool(managed_pid and _pid_alive(managed_pid))
    listener_pids = find_api_server_pids(port)
    current_pids = _current_process_pids()

    if reachable:
        if managed_alive and managed_pid in listener_pids:
            source = "ui"
            active_pid = managed_pid
        elif listener_pids and any(pid in current_pids for pid in listener_pids):
            source = "current"
            active_pid = next((pid for pid in listener_pids if pid in current_pids), listener_pids[0])
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
    all_port_pids = _find_listener_pids(port)
    if all_port_pids and not listener_pids:
        port_in_use_by_other = True

    return {
        "url": url,
        "health_url": health_url,
        "host": host,
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
        "stopping_self": would_stop_current_process(port),
    }


def start_server(*, host: str | None = None, port: int | None = None) -> tuple[bool, str]:
    host = host or DEFAULT_HOST
    port = port if port is not None else DEFAULT_PORT
    url = build_api_url(host=host, port=port)
    health_url = build_health_url(host=host, port=port)
    status = get_server_status(host=host, port=port)

    if status["reachable"]:
        if status["source"] == "external":
            return False, (
                f"API server already running externally (pid {status['active_pid']}) at {url}. "
                "Use **Stop server** first if you want to restart from this app."
            )
        return False, f"API server already reachable at {url}"

    blocking = [pid for pid in _find_listener_pids(port) if pid not in status["listener_pids"]]
    if blocking:
        return False, (
            f"Port {port} is already in use by pid {blocking[0]}. "
            "Stop that process before starting the API server."
        )

    env = apply_managed_settings_to_env()
    env["API_HOST"] = host
    env["API_PORT"] = str(port)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_PATH.open("a", encoding="utf-8")
    log_handle.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_handle.flush()

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--reload",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(PROJECT_DIR),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _write_pid(proc.pid)

    for _ in range(30):
        time.sleep(0.5)
        if check_api_server(health_url):
            return True, f"Started API server (pid {proc.pid}) at {url}"
        if proc.poll() is not None:
            _clear_pid()
            tail = get_server_log_tail(20)
            return False, f"Server exited early (code {proc.returncode}).\n{tail}"

    return False, (
        f"Process started (pid {proc.pid}) but {url} is not reachable yet. "
        "Check the server log below."
    )


def stop_server(*, host: str | None = None, port: int | None = None) -> tuple[bool, str]:
    port = port if port is not None else DEFAULT_PORT
    health_url = build_health_url(host=host, port=port)
    pids = find_api_server_pids(port)

    if not pids:
        _clear_pid()
        if check_api_server(health_url) and _listener_serves_datapro_api(port):
            pids = _find_listener_pids(port)
        if not pids:
            if check_api_server(health_url):
                return False, (
                    f"Server is still reachable at {build_api_url(host=host, port=port)}, but its process "
                    f"could not be found on port {port}. Stop it manually in your terminal."
                )
            return False, "No API server is running on the configured port."

    stopped, errors = _stop_pids(pids)

    _clear_pid()
    time.sleep(0.5)

    if check_api_server(health_url):
        remaining = find_api_server_pids(port)
        if remaining:
            return False, (
                f"Sent stop signal to pid(s) {stopped}, but server is still running "
                f"(pid(s) {remaining}). Stop manually in your terminal."
            )
        return False, f"Stop signal sent, but {build_api_url(host=host, port=port)} is still reachable."

    if errors:
        return False, "\n".join(errors)

    label = ", ".join(str(pid) for pid in stopped)
    return True, f"Stopped API server (pid {label})."


def run_stop_server_subprocess(*, host: str | None = None, port: int | None = None) -> tuple[bool, str]:
    """
    Stop via a fresh Python process so orphaned uvicorn workers get current stop logic.
    The running API handler may be stale code loaded at worker spawn time.
    """
    host = host or DEFAULT_HOST
    port = port if port is not None else DEFAULT_PORT
    script = (
        "from api_process import stop_server; "
        "ok, msg = stop_server("
        f"host={host!r}, port={port}"
        "); "
        "print(msg); "
        "import sys; "
        "sys.exit(0 if ok else 1)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    message = (result.stdout or result.stderr or "").strip() or "Stop failed"
    if result.returncode == 0:
        return True, message.splitlines()[-1] if message else "Stopped API server."
    return False, message.splitlines()[-1] if message else "Failed to stop API server."


def delayed_stop(*, host: str | None = None, port: int | None = None, delay: float = 0.75) -> None:
    time.sleep(delay)
    run_stop_server_subprocess(host=host, port=port)


def restart_server(*, host: str | None = None, port: int | None = None) -> tuple[bool, str]:
    host = host or DEFAULT_HOST
    port = port if port is not None else DEFAULT_PORT
    status = get_server_status(host=host, port=port)
    stop_msg = "Server was not running."

    if status["reachable"] or status["listener_pids"]:
        if status["stopping_self"]:
            if not RESTARTER_PATH.exists():
                return False, "Restart helper script is missing."
            subprocess.Popen(
                [sys.executable, str(RESTARTER_PATH), host, str(port)],
                cwd=str(PROJECT_DIR),
                start_new_session=True,
            )
            threading.Thread(
                target=delayed_stop,
                kwargs={"host": host, "port": port, "delay": 0.5},
                daemon=True,
            ).start()
            return True, (
                f"Restarting API server at {build_api_url(host=host, port=port)}. "
                "The page may disconnect briefly."
            )

        stop_ok, stop_msg = run_stop_server_subprocess(host=host, port=port)
        if not stop_ok and get_server_status(host=host, port=port)["reachable"]:
            return False, stop_msg
        time.sleep(0.5)

    start_ok, start_msg = start_server(host=host, port=port)
    if start_ok:
        if status["reachable"] or status["listener_pids"]:
            return True, f"{stop_msg}\n{start_msg}"
        return True, start_msg
    return False, start_msg
