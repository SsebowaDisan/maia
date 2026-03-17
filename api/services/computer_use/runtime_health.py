"""Computer Use runtime health checks.

Single responsibility:
validate local Ollama runtime reachability and model availability.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


@dataclass
class RuntimeHealthResult:
    ok: bool
    error: str = ""


def check_ollama_runtime(*, base_url: str, model: str, timeout_seconds: float = 3.0) -> RuntimeHealthResult:
    """Validate Ollama runtime is reachable and the model exists locally."""
    api_root = _strip_openai_v1(base_url)
    version_url = f"{api_root}/api/version"
    tags_url = f"{api_root}/api/tags"

    version_payload = _get_json(version_url, timeout_seconds=timeout_seconds)
    if version_payload is None:
        return RuntimeHealthResult(
            ok=False,
            error=f"Ollama runtime is unreachable at {api_root}.",
        )

    if not model:
        return RuntimeHealthResult(ok=True)

    tags_payload = _get_json(tags_url, timeout_seconds=timeout_seconds)
    if not isinstance(tags_payload, dict):
        return RuntimeHealthResult(
            ok=False,
            error="Could not read Ollama model catalog from /api/tags.",
        )

    rows = tags_payload.get("models")
    if not isinstance(rows, list):
        return RuntimeHealthResult(
            ok=False,
            error="Ollama model catalog payload is invalid.",
        )

    normalized_target = _normalize_model(model)
    available = {
        _normalize_model(str(row.get("name") or ""))
        for row in rows
        if isinstance(row, dict)
    }
    if normalized_target and normalized_target not in available:
        return RuntimeHealthResult(
            ok=False,
            error=f"Model '{normalized_target}' is not available in local Ollama. Pull it first.",
        )

    return RuntimeHealthResult(ok=True)


def _get_json(url: str, *, timeout_seconds: float) -> dict[str, Any] | list[Any] | None:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError, TimeoutError, OSError):
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def _normalize_model(value: str) -> str:
    model = str(value or "").strip()
    if model.lower().startswith("ollama::"):
        model = model.split("::", 1)[1].strip()
    return model


def _strip_openai_v1(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if normalized.endswith("/v1"):
        return normalized[:-3]
    return normalized
