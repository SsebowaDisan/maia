from __future__ import annotations

import json
import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

INFO_TABS = ("evidence", "claims", "sources")
SIGNAL_KEYS = ("evidence", "claims", "sources")
EMPTY_KEYS = ("evidence", "claims", "sources")


def _clean_text(value: Any, *, max_len: int = 220) -> str:
    return " ".join(str(value or "").split()).strip()[:max_len]


def _clean_list(value: Any, *, limit: int, item_max_len: int) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    seen: set[str] = set()
    for raw in value[: max(1, int(limit) * 3)]:
        text = _clean_text(raw, max_len=item_max_len)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(text)
        if len(rows) >= limit:
            break
    return rows


def _clean_dict(value: Any, *, allowed_keys: tuple[str, ...], max_len: int) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key in allowed_keys:
        text = _clean_text(value.get(key), max_len=max_len)
        if text:
            cleaned[key] = text
    return cleaned


def _to_plain_text(html_text: str, *, max_len: int = 2800) -> str:
    raw = str(html_text or "")
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _normalize_payload(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    tab_labels = _clean_dict(raw.get("tab_labels"), allowed_keys=INFO_TABS, max_len=28)
    signal_labels = _clean_dict(raw.get("signal_labels"), allowed_keys=SIGNAL_KEYS, max_len=26)
    empty_states = _clean_dict(raw.get("empty_states"), allowed_keys=EMPTY_KEYS, max_len=180)
    panel_title = _clean_text(raw.get("panel_title"), max_len=42)
    signal_title = _clean_text(raw.get("signal_title"), max_len=32)
    support_subtitle = _clean_text(raw.get("support_subtitle"), max_len=72)
    focus_claim_label = _clean_text(raw.get("focus_claim_label"), max_len=32)
    source_dominance_label = _clean_text(raw.get("source_dominance_label"), max_len=96)
    citation_strength_legend = _clean_text(raw.get("citation_strength_legend"), max_len=140)

    normalized: dict[str, Any] = {}
    if panel_title:
        normalized["panel_title"] = panel_title
    if signal_title:
        normalized["signal_title"] = signal_title
    if support_subtitle:
        normalized["support_subtitle"] = support_subtitle
    if focus_claim_label:
        normalized["focus_claim_label"] = focus_claim_label
    if source_dominance_label:
        normalized["source_dominance_label"] = source_dominance_label
    if citation_strength_legend:
        normalized["citation_strength_legend"] = citation_strength_legend
    if tab_labels:
        normalized["tab_labels"] = tab_labels
    if signal_labels:
        normalized["signal_labels"] = signal_labels
    if empty_states:
        normalized["empty_states"] = empty_states
    return normalized


def build_info_panel_copy(
    *,
    request_message: str,
    answer_text: str,
    info_html: str,
    mode: str,
    next_steps: list[str] | None = None,
    web_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not env_bool("MAIA_INFO_PANEL_DYNAMIC_COPY_ENABLED", default=True):
        return {}

    message = _clean_text(request_message, max_len=600)
    answer = _clean_text(answer_text, max_len=6000)
    info_excerpt = _to_plain_text(info_html, max_len=2400)
    if not message and not answer:
        return {}

    payload = {
        "mode": _clean_text(mode, max_len=24) or "ask",
        "request_message": message,
        "answer_excerpt": answer,
        "retrieval_excerpt": info_excerpt,
        "next_steps": _clean_list(next_steps or [], limit=8, item_max_len=120),
        "web_summary": sanitize_json_value(web_summary or {}),
    }
    prompt = (
        "Generate adaptive UI copy for Maia's information panel.\n"
        "Return one JSON object only with this shape:\n"
        '{'
        '"panel_title":"string",'
        '"signal_title":"string",'
        '"support_subtitle":"string",'
        '"focus_claim_label":"string",'
        '"source_dominance_label":"string",'
        '"citation_strength_legend":"string",'
        '"tab_labels":{"evidence":"string","claims":"string","sources":"string"},'
        '"signal_labels":{"evidence":"string","claims":"string","sources":"string"},'
        '"empty_states":{"evidence":"string","claims":"string","sources":"string"}'
        "}\n"
        "Rules:\n"
        "- Tailor wording to this exact request/answer context.\n"
        "- Avoid fixed reusable templates and generic marketing language.\n"
        "- Keep concise professional wording for UI labels.\n"
        "- Do not invent facts outside provided payload.\n"
        "- No markdown, no commentary, JSON object only.\n\n"
        f"Payload:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You are Maia's UX microcopy writer. "
            "You produce concise adaptive UI text and return strict JSON."
        ),
        user_prompt=prompt,
        temperature=0.2,
        timeout_seconds=12,
        max_tokens=1400,
    )
    return _normalize_payload(response if isinstance(response, dict) else None)
