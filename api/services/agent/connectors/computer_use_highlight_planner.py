from __future__ import annotations

import json
import os
from typing import Any

from api.services.computer_use.runtime_config import (
    normalize_model_name,
    resolve_effective_model,
    resolve_openai_base_url,
)

_MAX_QUERY_CHARS = 360
_MAX_TEXT_CHARS = 12000
_MAX_JSON_CHARS = 8000


def plan_llm_highlights(
    *,
    user_query: str,
    page_text: str,
    user_settings: dict[str, Any] | None = None,
    max_items: int = 8,
) -> dict[str, list[str]]:
    """Return LLM-selected terms/sentences relevant to the user query."""
    query = " ".join(str(user_query or "").split()).strip()[:_MAX_QUERY_CHARS]
    text = " ".join(str(page_text or "").split()).strip()[:_MAX_TEXT_CHARS]
    if not query or not text:
        return {"terms": [], "sentences": []}

    payload = _llm_json(
        query=query,
        text=text,
        user_settings=user_settings or {},
        max_items=max(1, min(12, int(max_items))),
    )
    if not isinstance(payload, dict):
        return {"terms": [], "sentences": []}

    terms = _normalize_list(payload.get("terms"), max_items=max_items, max_len=72)
    sentences = _normalize_list(payload.get("sentences"), max_items=max_items, max_len=220)
    return {"terms": terms, "sentences": sentences}


def _llm_json(
    *,
    query: str,
    text: str,
    user_settings: dict[str, Any],
    max_items: int,
) -> dict[str, Any] | None:
    try:
        from openai import OpenAI  # type: ignore[import]
    except Exception:
        return None

    model, _ = resolve_effective_model(user_settings=user_settings)
    normalized_model = normalize_model_name(model)
    if not normalized_model or normalized_model.lower().startswith("claude"):
        return None

    base_url, _ = resolve_openai_base_url(
        model=normalized_model,
        user_settings=user_settings,
    )
    api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip() or "not-required"
    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = (
        "You select browser highlight targets for a user question.\n"
        "Return strict JSON only with this shape:\n"
        '{"terms":["..."],"sentences":["..."]}\n'
        f"- Select up to {max_items} terms and {max_items} sentences.\n"
        "- Terms must be short phrases from the provided page text.\n"
        "- Sentences must be exact/near-exact excerpts from the provided page text.\n"
        "- Focus only on text that answers the user query.\n"
        "- Do not add explanations.\n\n"
        f"User query:\n{query}\n\n"
        f"Page text:\n{text}"
    )
    try:
        completion = client.chat.completions.create(
            model=normalized_model,
            messages=[
                {"role": "system", "content": "Return strict JSON only. No markdown."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=700,
        )
    except Exception:
        return None
    try:
        content = str(completion.choices[0].message.content or "").strip()
    except Exception:
        return None
    return _parse_json_obj(content)


def _parse_json_obj(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()[:_MAX_JSON_CHARS]
    if not text:
        return None
    # Accept fenced responses from permissive runtimes.
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except Exception:
            return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_list(raw: Any, *, max_items: int, max_len: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        cleaned = " ".join(str(item or "").split()).strip()
        if not cleaned:
            continue
        trimmed = cleaned[:max_len]
        if trimmed not in out:
            out.append(trimmed)
        if len(out) >= max(1, int(max_items)):
            break
    return out
