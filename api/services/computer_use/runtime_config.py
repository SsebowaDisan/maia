"""Computer Use runtime model/base-url resolution.

Single responsibility:
resolve the effective Computer Use model, provider routing hints, and
OpenAI-compatible runtime base URL in one place.
"""
from __future__ import annotations

import os
from typing import Any

from .runtime_health import check_ollama_runtime

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OPEN_SOURCE_MODEL = "qwen2.5vl:7b"


def normalize_model_name(model: str | None) -> str:
    value = str(model or "").strip()
    if value.lower().startswith("ollama::"):
        value = value.split("::", 1)[1].strip()
    return value


def is_anthropic_model(model: str | None) -> bool:
    return normalize_model_name(model).lower().startswith("claude")


def is_open_source_model(model: str | None) -> bool:
    raw = str(model or "").strip().lower()
    if not raw:
        return False
    if raw.startswith("ollama::"):
        return True

    normalized = normalize_model_name(raw).lower()
    if not normalized:
        return False

    proprietary_prefixes = ("gpt", "o1", "o3", "o4", "claude", "gemini")
    if normalized.startswith(proprietary_prefixes):
        return False

    oss_prefixes = (
        "qwen",
        "llama",
        "mistral",
        "mixtral",
        "gemma",
        "deepseek",
        "phi",
        "yi",
        "llava",
        "minicpm",
    )
    if normalized.startswith(oss_prefixes):
        return True

    return ":" in normalized


def resolve_effective_model(
    *,
    explicit_model: str | None = None,
    user_settings: dict[str, Any] | None = None,
) -> tuple[str, str]:
    explicit = str(explicit_model or "").strip()
    if explicit:
        return explicit, "explicit"

    settings = user_settings or {}

    stored = str(settings.get("agent.computer_use_model", "")).strip()
    if stored:
        return stored, "settings:agent.computer_use_model"

    env_model = str(os.environ.get("COMPUTER_USE_MODEL", "")).strip()
    if env_model:
        return env_model, "env:COMPUTER_USE_MODEL"

    ollama_setting_model = str(settings.get("agent.ollama.default_model", "")).strip()
    if ollama_setting_model:
        return ollama_setting_model, "settings:agent.ollama.default_model"

    active_model = str(active_ollama_model() or "").strip()
    if active_model:
        return active_model, "runtime:active_ollama_model"

    chat_env = str(os.environ.get("OPENAI_CHAT_MODEL", "")).strip()
    if chat_env:
        return chat_env, "env:OPENAI_CHAT_MODEL"

    return DEFAULT_OPEN_SOURCE_MODEL, "default:open_source"


def resolve_openai_base_url(
    *,
    model: str,
    user_settings: dict[str, Any] | None = None,
) -> tuple[str, str]:
    raw_model = str(model or "").strip()
    settings = user_settings or {}

    # Explicit Ollama model prefix should always use the Ollama base URL.
    if raw_model.lower().startswith("ollama::"):
        ollama_base = _resolve_ollama_base_url(settings=settings)
        return _openai_compatible_base_url(ollama_base), "ollama:model-prefix"

    env_base = str(os.environ.get("OPENAI_API_BASE", "")).strip()
    if env_base:
        return env_base.rstrip("/"), "env:OPENAI_API_BASE"

    # Prefer local OpenAI-compatible runtime for OSS models and keyless setups.
    if is_open_source_model(raw_model) or not str(os.environ.get("OPENAI_API_KEY", "")).strip():
        ollama_base = _resolve_ollama_base_url(settings=settings)
        return _openai_compatible_base_url(ollama_base), "ollama:auto"

    return DEFAULT_OPENAI_BASE_URL, "default:openai"


def validate_runtime_requirements(
    *,
    model: str | None = None,
    user_settings: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    resolved_model, _ = resolve_effective_model(
        explicit_model=model,
        user_settings=user_settings,
    )

    if is_anthropic_model(resolved_model):
        if str(os.environ.get("ANTHROPIC_API_KEY", "")).strip():
            return True, ""
        return (
            False,
            "ANTHROPIC_API_KEY is not configured for the selected Claude Computer Use model.",
        )

    base_url, base_source = resolve_openai_base_url(model=resolved_model, user_settings=user_settings)
    if base_url == DEFAULT_OPENAI_BASE_URL and not str(os.environ.get("OPENAI_API_KEY", "")).strip():
        return (
            False,
            "OPENAI_API_KEY is not configured and no local OpenAI-compatible runtime was resolved.",
        )

    if base_source.startswith("ollama:"):
        health = check_ollama_runtime(base_url=base_url, model=resolved_model)
        if not health.ok:
            return False, health.error

    return True, ""


def _resolve_ollama_base_url(*, settings: dict[str, Any]) -> str:
    candidate = (
        str(settings.get("agent.ollama.base_url") or "").strip()
        or str(os.environ.get("OLLAMA_BASE_URL", "")).strip()
        or DEFAULT_OLLAMA_BASE_URL
    )
    return _normalize_ollama_base_url(candidate)


def _normalize_ollama_base_url(value: str | None) -> str:
    base = str(value or DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        return f"http://{base}"
    return base


def _openai_compatible_base_url(ollama_base_url: str) -> str:
    return f"{_normalize_ollama_base_url(ollama_base_url)}/v1"


def active_ollama_model() -> str | None:
    """Best-effort access to the active Ollama model without hard import deps."""
    try:
        from api.services.ollama.model_sync import active_ollama_model as _active_model

        return _active_model()
    except Exception:
        return None
