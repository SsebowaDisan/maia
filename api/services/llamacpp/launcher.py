from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from api.services.llamacpp.errors import LlamaCppError
from api.services.llamacpp.service import LlamaCppService

# Module-level PID registry: port → pid
_server_pids: dict[int, int] = {}


def is_llamacpp_installed() -> bool:
    """Return True if llama-cpp-python is importable."""
    return importlib.util.find_spec("llama_cpp") is not None


def get_server_pid(port: int) -> int | None:
    return _server_pids.get(int(port))


def _build_server_command(
    *,
    model_path: Path,
    host: str,
    port: int,
    n_gpu_layers: int,
    n_ctx: int,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "llama_cpp.server",
        "--model",
        str(model_path),
        "--host",
        host,
        "--port",
        str(port),
        "--n_gpu_layers",
        str(n_gpu_layers),
        "--n_ctx",
        str(n_ctx),
    ]


def start_llamacpp_server(
    *,
    model_path: Path,
    host: str = "127.0.0.1",
    port: int = 8082,
    n_gpu_layers: int = -1,
    n_ctx: int = 4096,
    wait_seconds: int = 20,
) -> dict[str, Any]:
    """Start a llama-cpp-python server for the given model.

    Returns a dict with keys: status, reachable, pid, base_url.
    Status values: already_running | started | starting | not_installed | failed.
    """
    base_url = f"http://{host}:{port}"
    service = LlamaCppService(base_url=base_url)

    # Already running?
    if service.is_reachable():
        pid = _server_pids.get(port)
        return {
            "status": "already_running",
            "reachable": True,
            "pid": pid,
            "base_url": base_url,
        }

    if not is_llamacpp_installed():
        raise LlamaCppError(
            code="llamacpp_not_installed",
            message=(
                "llama-cpp-python is not installed. "
                "Run: pip install 'llama-cpp-python[server]'"
            ),
            status_code=503,
        )

    if not model_path.exists():
        raise LlamaCppError(
            code="llamacpp_model_not_found",
            message=f"Model file not found: {model_path.name}",
            status_code=404,
            details={"path": str(model_path)},
        )

    cmd = _build_server_command(
        model_path=model_path,
        host=host,
        port=port,
        n_gpu_layers=n_gpu_layers,
        n_ctx=n_ctx,
    )
    env = {**os.environ}

    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(cmd, **kwargs)
    except Exception as exc:
        raise LlamaCppError(
            code="llamacpp_start_failed",
            message=f"Failed to start llama-cpp-python server: {exc}",
            status_code=500,
            details={"error": str(exc)},
        ) from exc

    pid = int(process.pid)
    _server_pids[port] = pid

    deadline = time.time() + max(5, int(wait_seconds))
    while time.time() < deadline:
        time.sleep(1.0)
        if service.is_reachable():
            return {
                "status": "started",
                "reachable": True,
                "pid": pid,
                "base_url": base_url,
            }

    # Still starting — process is alive but not yet ready
    return {
        "status": "starting",
        "reachable": False,
        "pid": pid,
        "base_url": base_url,
    }


def stop_llamacpp_server(*, port: int = 8082) -> dict[str, Any]:
    """Stop the server running on the given port (by stored PID)."""
    pid = _server_pids.get(port)
    if pid is None:
        return {"status": "not_running", "port": port}

    try:
        if sys.platform.startswith("win"):
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(pid, signal.SIGTERM)
        _server_pids.pop(port, None)
        return {"status": "stopped", "pid": pid, "port": port}
    except ProcessLookupError:
        _server_pids.pop(port, None)
        return {"status": "already_stopped", "pid": pid, "port": port}
    except Exception as exc:
        raise LlamaCppError(
            code="llamacpp_stop_failed",
            message=f"Failed to stop server: {exc}",
            status_code=500,
            details={"pid": pid, "port": port},
        ) from exc
