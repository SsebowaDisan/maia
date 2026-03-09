from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
            "pull_model": "ollama pull qwen3:8b",
            "pull_embedding": "ollama pull embeddinggemma",
        },
        "tips": [
            "Install Ollama once, then keep it running in background.",
            "If the service is not running, click `Start Ollama` in Settings (auto-installs on Windows if missing).",
            "After startup, download model(s) and select default.",
        ],
    }


def _is_local_base_url(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost"}


def _find_ollama_binary() -> str | None:
    path_binary = shutil.which("ollama")
    if path_binary:
        return path_binary

    if platform.system().lower().startswith("win"):
        local_app = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "")
        candidates = [
            Path(local_app) / "Programs" / "Ollama" / "ollama.exe",
            Path(program_files) / "Ollama" / "ollama.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    return None


def _install_ollama_windows(*, install_url: str) -> dict[str, Any]:
    installer_path = str(Path(os.environ.get("TEMP", "")) / "OllamaSetup.exe")
    script = (
        "$ProgressPreference='SilentlyContinue';"
        f"$u='{install_url}';"
        f"$p='{installer_path}';"
        "Invoke-WebRequest -Uri $u -OutFile $p;"
        "Start-Process -FilePath $p -ArgumentList '/S'"
    )
    try:
        process = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        raise OllamaError(
            code="ollama_install_failed",
            message="Failed to install Ollama automatically.",
            status_code=500,
            details={"installer": installer_path, "error": str(exc)},
        ) from exc

    return {
        "installer": installer_path,
        "installer_pid": int(process.pid or 0) or None,
        "binary": _find_ollama_binary(),
    }


def start_local_ollama(*, base_url: str, wait_seconds: int = 10, auto_install: bool = True) -> dict[str, Any]:
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

    binary = _find_ollama_binary()
    install_result: dict[str, Any] | None = None
    if not binary and auto_install and platform.system().lower().startswith("win") and _is_local_base_url(base_url):
        install_result = _install_ollama_windows(install_url="https://ollama.com/download/OllamaSetup.exe")
        binary = install_result.get("binary")
        if not binary:
            return {
                "status": "installing",
                "reachable": False,
                "version": None,
                "pid": install_result.get("installer_pid"),
                "install": install_result,
            }

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
        if not binary:
            raise FileNotFoundError("ollama binary not found")
        process = subprocess.Popen([binary, "serve"], **kwargs)
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
                "install": install_result,
            }
        except OllamaError as exc:
            last_error = exc

    return {
        "status": "starting",
        "reachable": False,
        "version": None,
        "pid": int(process.pid or 0) or None,
        "error": last_error.to_detail() if last_error else None,
        "install": install_result,
    }
