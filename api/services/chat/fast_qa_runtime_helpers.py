from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests


def _is_google_gemini_compatible_base(base_url: str) -> bool:
    normalized = str(base_url or "").strip().lower()
    return "generativelanguage.googleapis.com" in normalized


def _prepare_openai_compatible_payload(*, base_url: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(request_payload or {})
    if _is_google_gemini_compatible_base(base_url):
        extra_body = payload.get("extra_body")
        merged_extra = dict(extra_body) if isinstance(extra_body, dict) else {}
        google_block = merged_extra.get("google")
        merged_google = dict(google_block) if isinstance(google_block, dict) else {}
        thinking_block = merged_google.get("thinking_config")
        merged_thinking = dict(thinking_block) if isinstance(thinking_block, dict) else {}
        merged_thinking.setdefault("thinking_budget", 0)
        merged_google["thinking_config"] = merged_thinking
        merged_extra["google"] = merged_google
        payload["extra_body"] = merged_extra
    return payload


def normalize_request_attachments(request: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in list(getattr(request, "attachments", []) or []):
        name_raw = str(getattr(item, "name", "") or "").strip()
        file_id_raw = str(getattr(item, "file_id", "") or "").strip()
        if not name_raw and not file_id_raw:
            continue
        name = " ".join(name_raw.split())[:220]
        file_id = " ".join(file_id_raw.split())[:160]
        dedupe_key = (file_id, name.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        payload = {"name": name or file_id or "Uploaded file"}
        if file_id:
            payload["file_id"] = file_id
        normalized.append(payload)
    return normalized


def extract_text_content(raw_content: Any) -> str:
    if isinstance(raw_content, str):
        return raw_content.strip()
    if not isinstance(raw_content, list):
        return ""
    parts: list[str] = []
    for item in raw_content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text_value = str(item.get("text") or "").strip()
        if text_value:
            parts.append(text_value)
    return "\n".join(parts).strip()


def call_openai_chat_text(
    *,
    api_key: str,
    base_url: str,
    request_payload: dict[str, Any],
    timeout_seconds: int,
    extract_text_content_fn,
) -> str | None:
    max_attempts_raw = str(os.getenv("MAIA_FAST_QA_LLM_RETRIES", "") or "").strip()
    try:
        max_attempts = int(max_attempts_raw) if max_attempts_raw else 3
    except Exception:
        max_attempts = 3
    max_attempts = max(1, min(max_attempts, 5))

    backoff_ms_raw = str(os.getenv("MAIA_FAST_QA_LLM_RETRY_BACKOFF_MS", "") or "").strip()
    try:
        base_backoff_ms = int(backoff_ms_raw) if backoff_ms_raw else 1000
    except Exception:
        base_backoff_ms = 1000
    base_backoff_ms = max(100, min(base_backoff_ms, 10000))

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        payload = _prepare_openai_compatible_payload(
            base_url=base_url,
            request_payload=request_payload,
        )
        try:
            response = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=max(8, int(timeout_seconds)),
            )
            response.raise_for_status()
            response_payload = response.json()
            choices = response_payload.get("choices")
            if not isinstance(choices, list) or not choices:
                return None
            first = choices[0]
            if not isinstance(first, dict):
                return None
            message = first.get("message")
            if not isinstance(message, dict):
                return None
            return extract_text_content_fn(message.get("content")) or None
        except requests.HTTPError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code not in {429, 500, 502, 503, 504} or attempt >= max_attempts:
                raise
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= max_attempts:
                raise

        delay_seconds = (base_backoff_ms / 1000.0) * (2 ** (attempt - 1))
        time.sleep(min(delay_seconds, 8.0))

    if last_error is not None:
        raise last_error
    return None


def parse_json_object(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def truncate_for_log(value: Any, limit: int = 1600) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(+{len(text) - limit} chars)"


def _compatible_config(
    config_fn,
    *,
    primary_key: str,
    legacy_key: str,
    default: str,
) -> str:
    primary_value = str(config_fn(primary_key, default="") or "").strip()
    if primary_value:
        return primary_value
    legacy_value = str(config_fn(legacy_key, default="") or "").strip()
    if legacy_value:
        return legacy_value
    return default


def infer_openai_compatible_provider(*, base_url: str, model: str) -> str:
    normalized_base = str(base_url or "").strip().lower()
    normalized_model = str(model or "").strip().lower()
    hostname = urlparse(normalized_base).hostname or ""

    if "dashscope" in normalized_base or normalized_model.startswith("qwen"):
        return "qwen-dashscope"
    if "api.openai.com" in normalized_base or normalized_model.startswith("gpt-"):
        return "openai"
    if "openai.azure.com" in normalized_base or "azure" in normalized_base:
        return "azure-openai"
    if "localhost" in hostname or "127.0.0.1" in hostname or "ollama" in normalized_base:
        return "local-openai-compatible"
    if "llamacpp" in normalized_base or "llama.cpp" in normalized_base:
        return "llamacpp-openai-compatible"
    if hostname:
        return hostname
    return "openai-compatible"


def resolve_fast_qa_llm_config(*, config_fn, is_placeholder_api_key_fn, llms_manager) -> tuple[str, str, str, str]:
    default_base = _compatible_config(
        config_fn,
        primary_key="MAIA_LLM_API_BASE",
        legacy_key="OPENAI_API_BASE",
        default="",
    )
    default_model = _compatible_config(
        config_fn,
        primary_key="MAIA_LLM_CHAT_MODEL",
        legacy_key="OPENAI_CHAT_MODEL",
        default="",
    )
    env_api_key = _compatible_config(
        config_fn,
        primary_key="MAIA_LLM_API_KEY",
        legacy_key="OPENAI_API_KEY",
        default="",
    )
    if not is_placeholder_api_key_fn(env_api_key) and default_base and default_model:
        return env_api_key, default_base, default_model, "env"

    try:
        default_name = str(llms_manager.get_default_name() or "").strip()
    except Exception:
        default_name = ""
    try:
        model_info = llms_manager.info().get(default_name, {}) if default_name else {}
    except Exception:
        model_info = {}
    spec = model_info.get("spec", {}) if isinstance(model_info, dict) else {}
    if not isinstance(spec, dict):
        spec = {}

    spec_api_key = str(spec.get("api_key") or "").strip()
    spec_base_url = str(spec.get("base_url") or spec.get("openai_api_base") or spec.get("api_base") or "").strip()
    spec_model = str(spec.get("model") or spec.get("model_name") or "").strip()
    if not is_placeholder_api_key_fn(spec_api_key) and spec_base_url and spec_model:
        return spec_api_key, spec_base_url or default_base, spec_model or default_model, f"llm:{default_name or 'default'}"

    return "", default_base, default_model, "missing"
