from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.services.llamacpp.errors import LlamaCppError

DEFAULT_MODEL_SUBDIR = "models/gguf"
_CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB chunks

RECOMMENDED_MODELS: list[dict[str, Any]] = [
    {
        "name": "Llama 3.2 3B — 2.0 GB (fast, recommended)",
        "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "size_gb": 2.0,
        "type": "chat",
        "recommended": True,
    },
    {
        "name": "Gemma 3 4B — 3.1 GB",
        "filename": "gemma-3-4b-it-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/gemma-3-4b-it-GGUF/resolve/main/gemma-3-4b-it-Q4_K_M.gguf",
        "size_gb": 3.1,
        "type": "chat",
        "recommended": True,
    },
    {
        "name": "Qwen3 8B — 5.2 GB (high quality)",
        "filename": "Qwen3-8B-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf",
        "size_gb": 5.2,
        "type": "chat",
        "recommended": False,
    },
    {
        "name": "Llama 3.1 8B — 4.9 GB",
        "filename": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "size_gb": 4.9,
        "type": "chat",
        "recommended": False,
    },
    {
        "name": "DeepSeek R1 8B — 5.0 GB (reasoning)",
        "filename": "DeepSeek-R1-Distill-Llama-8B-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF/resolve/main/DeepSeek-R1-Distill-Llama-8B-Q4_K_M.gguf",
        "size_gb": 5.0,
        "type": "chat",
        "recommended": False,
    },
    {
        "name": "nomic-embed-text v1.5 — 274 MB (embedding)",
        "filename": "nomic-embed-text-v1.5.Q8_0.gguf",
        "url": "https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.Q8_0.gguf",
        "size_gb": 0.27,
        "type": "embedding",
        "recommended": True,
    },
]


def get_model_dir(settings: dict[str, Any]) -> Path:
    raw = str(settings.get("agent.llamacpp.model_dir") or "").strip()
    if raw:
        return Path(raw)
    base = Path(os.getenv("MAIA_DATA_DIR", "data"))
    return base / DEFAULT_MODEL_SUBDIR


def list_local_models(settings: dict[str, Any]) -> list[dict[str, Any]]:
    model_dir = get_model_dir(settings)
    if not model_dir.exists():
        return []
    results = []
    for path in sorted(model_dir.glob("*.gguf")):
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        results.append({
            "filename": path.name,
            "size_bytes": size,
            "path": str(path),
        })
    return results


def download_model(
    *,
    url: str,
    filename: str,
    model_dir: Path,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    model_dir.mkdir(parents=True, exist_ok=True)
    dest_path = model_dir / filename
    tmp_path = model_dir / f"{filename}.download"

    req = Request(url, headers={"User-Agent": "MAIA/1.0"})
    try:
        with urlopen(req, timeout=60) as response:
            total_bytes = int(response.headers.get("Content-Length") or 0)
            bytes_downloaded = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = response.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
                    if on_progress:
                        pct = (bytes_downloaded / total_bytes * 100.0) if total_bytes > 0 else 0.0
                        on_progress({
                            "percent": round(min(pct, 99.9), 1),
                            "bytes_downloaded": bytes_downloaded,
                            "total_bytes": total_bytes,
                        })
    except HTTPError as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise LlamaCppError(
            code="llamacpp_download_failed",
            message=f"Failed to download model: HTTP {exc.code}",
            status_code=502,
            details={"url": url, "filename": filename},
        ) from exc
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise LlamaCppError(
            code="llamacpp_download_failed",
            message=f"Failed to download model: {exc}",
            status_code=502,
            details={"url": url, "filename": filename},
        ) from exc

    tmp_path.rename(dest_path)
    size_bytes = dest_path.stat().st_size
    if on_progress:
        on_progress({"percent": 100.0, "bytes_downloaded": size_bytes, "total_bytes": size_bytes})
    return {"filename": filename, "size_bytes": size_bytes, "path": str(dest_path)}


def delete_model(*, filename: str, model_dir: Path) -> None:
    path = model_dir / filename
    if path.exists():
        path.unlink()
