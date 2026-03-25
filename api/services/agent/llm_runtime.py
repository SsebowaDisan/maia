from __future__ import annotations

import json
import os
import re
import time
import logging
from typing import Any, Generator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.services.agent.observability import get_agent_observability

logger = logging.getLogger(__name__)

PLACEHOLDER_API_KEYS = {
    "",
    "your-key",
    "<your_openai_key>",
    "changeme",
    "none",
    "null",
}
JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
DEFAULT_OPENAI_BASE = ""
DEFAULT_OPENAI_MODEL = ""


def _is_google_gemini_compatible_base(base_url: str) -> bool:
    normalized = str(base_url or "").strip().lower()
    return "generativelanguage.googleapis.com" in normalized


def _env_or_config(name: str, default: str = "") -> str:
    value = str(os.getenv(name, "")).strip()
    if value:
        return value
    try:
        from decouple import config  # type: ignore[import-not-found]

        return str(config(name, default=default) or "").strip()
    except Exception:
        return str(default or "").strip()


def _compatible_env(primary_name: str, legacy_name: str, default: str = "") -> str:
    primary_value = _env_or_config(primary_name, "")
    if primary_value:
        return primary_value
    legacy_value = _env_or_config(legacy_name, "")
    if legacy_value:
        return legacy_value
    return str(default or "").strip()


def env_bool(name: str, *, default: bool) -> bool:
    raw = _env_or_config(name, "").lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = _env_or_config(name, "")
    try:
        value = int(raw)
    except Exception:
        value = int(default)
    value = max(int(minimum), value)
    value = min(int(maximum), value)
    return value


def openai_api_key() -> str:
    return _compatible_env("MAIA_LLM_API_KEY", "OPENAI_API_KEY", "")


def has_openai_credentials() -> bool:
    key = openai_api_key()
    if key.lower() not in PLACEHOLDER_API_KEYS:
        return bool(_openai_base_url() and _openai_chat_model())
    # Local OpenAI-compatible runtimes often run without a real key.
    return bool(_openai_base_url() and _openai_chat_model())


def _openai_base_url() -> str:
    return _compatible_env("MAIA_LLM_API_BASE", "OPENAI_API_BASE", DEFAULT_OPENAI_BASE).strip()


def _openai_chat_model() -> str:
    return _compatible_env("MAIA_LLM_CHAT_MODEL", "OPENAI_CHAT_MODEL", DEFAULT_OPENAI_MODEL).strip()


def _openai_fallback_models() -> list[str]:
    raw = _compatible_env("MAIA_LLM_CHAT_MODEL_FALLBACKS", "OPENAI_CHAT_MODEL_FALLBACKS", "")
    if not raw:
        raw = _env_or_config("MAIA_AGENT_LLM_MODEL_FALLBACKS", "")
    if not raw:
        return []
    models = [item.strip() for item in raw.split(",")]
    return [item for item in models if item]


def _candidate_models(model: str | None, *, include_fallbacks: bool) -> list[str]:
    primary = str(model or _openai_chat_model()).strip()
    candidates = [primary]
    if include_fallbacks:
        candidates.extend(_openai_fallback_models())
    deduped: list[str] = []
    for item in candidates:
        if not item or item in deduped:
            continue
        deduped.append(item)
    return deduped


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


def parse_json_object(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except Exception:
        match = JSON_OBJECT_RE.search(text)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None


def sanitize_json_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 3:
        return str(value)[:300]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:1200]
    if isinstance(value, list):
        return [sanitize_json_value(item, depth=depth + 1) for item in value[:24]]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in list(value.items())[:24]:
            if not isinstance(key, str):
                continue
            cleaned[key[:80]] = sanitize_json_value(item, depth=depth + 1)
        return cleaned
    return str(value)[:300]


def call_openai_chat(
    *,
    messages: list[dict[str, Any]],
    temperature: float = 0.0,
    timeout_seconds: int = 18,
    model: str | None = None,
    max_tokens: int | None = None,
    retries: int | None = None,
    enable_thinking: bool | None = None,
    use_fallback_models: bool | None = None,
) -> dict[str, Any] | None:
    if not has_openai_credentials():
        return None
    if isinstance(retries, int):
        max_attempts = max(1, min(int(retries), 5))
    else:
        max_attempts = _env_int("MAIA_AGENT_LLM_RETRIES", default=2, minimum=1, maximum=5)
    base_backoff_ms = _env_int(
        "MAIA_AGENT_LLM_RETRY_BACKOFF_MS",
        default=250,
        minimum=100,
        maximum=4000,
    )
    base_url = f"{_openai_base_url().rstrip('/')}/chat/completions"
    timeout_value = max(8, int(timeout_seconds))
    include_fallbacks = (
        bool(use_fallback_models)
        if isinstance(use_fallback_models, bool)
        else env_bool("MAIA_AGENT_LLM_USE_FALLBACK_MODELS", default=True)
    )
    for model_name in _candidate_models(model, include_fallbacks=include_fallbacks):
        for attempt in range(1, max_attempts + 1):
            payload: dict[str, Any] = {
                "model": model_name,
                "temperature": max(0.0, min(1.0, float(temperature))),
                "messages": messages,
            }
            if isinstance(max_tokens, int) and max_tokens > 0:
                payload["max_tokens"] = max_tokens
            thinking_flag = _resolve_enable_thinking(
                model_name=model_name,
                explicit_value=enable_thinking,
            )
            if isinstance(thinking_flag, bool):
                payload["enable_thinking"] = thinking_flag
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
            request_obj = Request(
                base_url,
                method="POST",
                headers={
                    "Authorization": (
                        f"Bearer {openai_api_key()}"
                        if openai_api_key()
                        else "Bearer not-required"
                    ),
                    "Content-Type": "application/json",
                },
                data=json.dumps(payload).encode("utf-8"),
            )
            try:
                with urlopen(request_obj, timeout=timeout_value) as response:
                    raw = response.read().decode("utf-8")
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        try:
                            get_agent_observability().observe_llm_usage(
                                model=model_name,
                                usage=parsed.get("usage")
                                if isinstance(parsed.get("usage"), dict)
                                else {},
                            )
                        except Exception:
                            pass
                        return parsed
                    break
            except HTTPError as exc:
                status = int(getattr(exc, "code", 0) or 0)
                should_retry = status in {408, 409, 425, 429} or status >= 500
                if should_retry and attempt < max_attempts:
                    time.sleep((base_backoff_ms / 1000.0) * (2 ** (attempt - 1)))
                    continue
                break
            except Exception:
                if attempt < max_attempts:
                    time.sleep((base_backoff_ms / 1000.0) * (2 ** (attempt - 1)))
                    continue
                break
    return None


def call_openai_chat_stream(
    *,
    messages: list[dict[str, Any]],
    temperature: float = 0.0,
    timeout_seconds: int = 60,
    model: str | None = None,
    max_tokens: int | None = None,
    enable_thinking: bool | None = None,
) -> Generator[str, None, None]:
    """Stream chat completions token-by-token.

    Yields text chunks as they arrive from the LLM. Works with OpenAI,
    Qwen/DashScope, and any OpenAI-compatible API that supports
    ``stream: true`` with SSE responses.
    """
    if not has_openai_credentials():
        return
    base_url = f"{_openai_base_url().rstrip('/')}/chat/completions"
    timeout_value = max(10, int(timeout_seconds))
    model_name = model or _primary_model()

    payload: dict[str, Any] = {
        "model": model_name,
        "temperature": max(0.0, min(1.0, float(temperature))),
        "messages": messages,
        "stream": True,
    }
    if isinstance(max_tokens, int) and max_tokens > 0:
        payload["max_tokens"] = max_tokens
    thinking_flag = _resolve_enable_thinking(
        model_name=model_name, explicit_value=enable_thinking,
    )
    if isinstance(thinking_flag, bool):
        payload["enable_thinking"] = thinking_flag

    request_obj = Request(
        base_url,
        method="POST",
        headers={
            "Authorization": f"Bearer {openai_api_key()}" if openai_api_key() else "Bearer not-required",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with urlopen(request_obj, timeout=timeout_value) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    except Exception as exc:
        logger.warning("Streaming LLM call failed: %s", exc)


def _resolve_enable_thinking(*, model_name: str, explicit_value: bool | None) -> bool | None:
    if isinstance(explicit_value, bool):
        return explicit_value
    base = _openai_base_url().lower()
    model = str(model_name or "").strip().lower()
    looks_like_qwen_runtime = "dashscope" in base or model.startswith("qwen")
    if not looks_like_qwen_runtime:
        return None
    return env_bool("MAIA_AGENT_LLM_ENABLE_THINKING_DEFAULT", default=False)


def first_message_text(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return extract_text_content(content)


def call_json_response(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    timeout_seconds: int = 18,
    max_tokens: int | None = None,
    retries: int | None = None,
    allow_json_repair: bool = True,
    enable_thinking: bool | None = None,
    use_fallback_models: bool | None = None,
) -> dict[str, Any] | None:
    payload = call_openai_chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
        retries=retries,
        enable_thinking=enable_thinking,
        use_fallback_models=use_fallback_models,
    )
    text = first_message_text(payload)
    if not text:
        return None
    parsed = parse_json_object(text)
    if parsed is not None:
        return parsed
    if not allow_json_repair:
        return None
    # JSON repair pass for occasional malformed model outputs.
    repair_payload = call_openai_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You repair malformed JSON outputs. Return one valid JSON object only. "
                    "No markdown, no commentary."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Rewrite the following model output as valid JSON object while preserving meaning.\n\n"
                    f"Original output:\n{text}"
                ),
            },
        ],
        temperature=0.0,
        timeout_seconds=min(max(8, timeout_seconds), 12),
        max_tokens=max_tokens,
        retries=retries,
        enable_thinking=False,
        use_fallback_models=False,
    )
    repaired_text = first_message_text(repair_payload)
    if not repaired_text:
        return None
    return parse_json_object(repaired_text)


def call_text_response(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    timeout_seconds: int = 18,
    max_tokens: int | None = None,
    retries: int | None = None,
    enable_thinking: bool | None = None,
    use_fallback_models: bool | None = None,
) -> str:
    payload = call_openai_chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
        retries=retries,
        enable_thinking=enable_thinking,
        use_fallback_models=use_fallback_models,
    )
    return first_message_text(payload)
