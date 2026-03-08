from __future__ import annotations

import json
import re
from typing import Any
from urllib.request import Request, urlopen


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
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(request_payload).encode("utf-8"),
    )
    with urlopen(request, timeout=max(8, int(timeout_seconds))) as response:
        payload = json.loads(response.read().decode("utf-8"))
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    return extract_text_content_fn(message.get("content")) or None


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


def resolve_fast_qa_llm_config(*, config_fn, is_placeholder_api_key_fn, llms_manager) -> tuple[str, str, str, str]:
    default_base = str(config_fn("OPENAI_API_BASE", default="https://api.openai.com/v1")) or "https://api.openai.com/v1"
    default_model = str(config_fn("OPENAI_CHAT_MODEL", default="gpt-4o-mini")) or "gpt-4o-mini"
    env_api_key = str(config_fn("OPENAI_API_KEY", default="") or "").strip()
    if not is_placeholder_api_key_fn(env_api_key):
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
    if not is_placeholder_api_key_fn(spec_api_key):
        return spec_api_key, spec_base_url or default_base, spec_model or default_model, f"llm:{default_name or 'default'}"

    return "", default_base, default_model, "missing"
