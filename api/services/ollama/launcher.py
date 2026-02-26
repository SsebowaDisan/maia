from __future__ import annotations

import platform
import subprocess
import time
from typing import Any

from api.services.ollama.errors import OllamaError
from api.services.ollama.service import OllamaService


def quickstart_payload(*, base_url: str) -> dict[str, Any]:
    system = platform.system().lower()
    if system.startswith("win"):
        install_url = "https://ollama.com/download/windows"
        command_check = "ollama --version"
        command_start = "ollama serve"
    elif system == "darwin":
        install_url = "https://ollama.com/download/mac"
        command_check = "ollama --version"
        command_start = "ollama serve"
    else:
        install_url = "https://ollama.com/download/linux"
        command_check = "ollama --version"
        command_start = "ollama serve"

    return {
        "platform": system,
        "base_url": base_url,
        "install_url": install_url,
        "commands": {
            "check": command_check,
            "start": command_start,
            "pull_model": "ollama pull llama3.2:3b",
            "pull_embedding": "ollama pull nomic-embed-text",
        },
        "tips": [
            "Install Ollama once, then keep it running in background.",
            "If the service is not running, click `Start Ollama` in Settings.",
            "After startup, download model(s) and select default.",
        ],
    }


def start_local_ollama(*, base_url: str, wait_seconds: int = 10) -> dict[str, Any]:
    service = OllamaService(base_url=base_url)
    try:
        version = service.get_version()
        return {
            "status": "already_running",
            "reachable": True,
            "version": version,
            "pid": None,
        }
    except OllamaError:
        pass

    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if platform.system().lower().startswith("win"):
        creationflags = 0
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(["ollama", "serve"], **kwargs)
    except FileNotFoundError as exc:
        raise OllamaError(
            code="ollama_binary_missing",
            message="Ollama CLI not found. Install Ollama and retry.",
            status_code=404,
            details={"install_url": quickstart_payload(base_url=base_url)["install_url"]},
        ) from exc
    except Exception as exc:
        raise OllamaError(
            code="ollama_start_failed",
            message="Failed to launch Ollama locally.",
            status_code=500,
            details={"error": str(exc)},
        ) from exc

    deadline = time.time() + max(2, int(wait_seconds))
    last_error: OllamaError | None = None
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            version = service.get_version()
            return {
                "status": "started",
                "reachable": True,
                "version": version,
                "pid": int(process.pid or 0) or None,
            }
        except OllamaError as exc:
            last_error = exc

    return {
        "status": "starting",
        "reachable": False,
        "version": None,
        "pid": int(process.pid or 0) or None,
        "error": last_error.to_detail() if last_error else None,
    }
