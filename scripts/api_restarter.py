#!/usr/bin/env python3
"""Wait for the API port to free, then start uvicorn (used when restarting in-place)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from settings_service import apply_managed_settings_to_env


def _port_in_use(port: int) -> bool:
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("API_HOST", "127.0.0.1")
    port = int(sys.argv[2] if len(sys.argv) > 2 else os.environ.get("API_PORT", "8080"))

    for _ in range(60):
        if not _port_in_use(port):
            break
        time.sleep(0.5)
    else:
        print(f"Port {port} did not become free in time.", file=sys.stderr)
        return 1

    env = apply_managed_settings_to_env()
    env["API_HOST"] = host
    env["API_PORT"] = str(port)
    log_path = PROJECT_DIR / ".api_server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    log_handle.write(f"\n--- restart {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
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
    (PROJECT_DIR / ".api_server.pid").write_text(str(proc.pid), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
