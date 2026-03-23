from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.parse import urlparse

from api.services.agent.llm_runtime import call_json_response, env_bool

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
STOPWORDS = {
    "about",
    "after",
    "also",
    "been",
    "being",
    "from",
    "have",
    "into",
    "more",
    "most",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "using",
    "with",
}
ACTION_TOOL_IDS = {
    "send_email": {"gmail.send", "email.send", "mailer.report_send"},
    "submit_contact_form": {"browser.contact_form.send"},
    "post_message": {"slack.post_message", "browser.contact_form.send"},
    "create_document": {"docs.create", "workspace.docs.fill_template", "workspace.docs.research_notes"},
    "update_sheet": {"workspace.sheets.append", "workspace.sheets.track_step"},
}


def _pick_first_nonempty(*values: Any) -> str:
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if text:
            return text
    return ""


def clean_text_list(raw: Any, *, limit: int, max_item_len: int = 220) -> list[str]:
    if not isinstance(raw, list):
        return []
    rows: list[str] = []
    for item in raw:
        text = " ".join(str(item or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in {value.lower() for value in rows}:
            continue
        rows.append(text[:max_item_len])
        if len(rows) >= max(1, int(limit)):
            break
    return rows


def extract_first_url(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    match = URL_RE.search(joined)
    return match.group(0).strip().rstrip(".,;)") if match else ""


def host_from_url(url: str) -> str:
    try:
        host = str(urlparse(str(url or "").strip()).hostname or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


def infer_source_origin_label(
    *,
    label: str = "",
    url: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    meta = metadata if isinstance(metadata, dict) else {}
    direct_origin = _pick_first_nonempty(
        meta.get("source_origin"),
        meta.get("origin"),
        meta.get("publisher"),
        meta.get("source_author"),
        meta.get("site_name"),
    )
    if direct_origin:
        return direct_origin[:120]
    label_text = _pick_first_nonempty(label, meta.get("title"))
    if label_text:
        return label_text[:120]
    host = host_from_url(url)
    if not host:
        return ""
    root = host.split(".")
    if len(root) >= 2:
        base = root[-2]
    else:
        base = host
    return base.replace("-", " ").replace("_", " ").strip().title()[:120]


def infer_source_scope_summary(
    *,
    label: str = "",
    url: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    meta = metadata if isinstance(metadata, dict) else {}
    return _pick_first_nonempty(
        meta.get("scope_topic"),
        meta.get("topic"),
        meta.get("branch"),
        meta.get("excerpt"),
        meta.get("snippet"),
        meta.get("text_excerpt"),
        meta.get("description"),
        meta.get("extract"),
        meta.get("goal"),
        meta.get("title"),
        label,
        url,
    )[:260]


def extract_source_evidence_lines(metadata: dict[str, Any] | None) -> list[str]:
    meta = metadata if isinstance(metadata, dict) else {}
    rows: list[str] = []
    for key in ("excerpt", "snippet", "text_excerpt", "description", "extract"):
        value = meta.get(key)
        text = " ".join(str(value or "").split()).strip()
        if text and text not in rows:
            rows.append(text[:260])
            if len(rows) >= 3:
                return rows
    raw_evidence = meta.get("evidence")
    if isinstance(raw_evidence, list):
        for item in raw_evidence[:6]:
            if isinstance(item, dict):
                field = " ".join(str(item.get("field") or "").split()).strip()
                quote = " ".join(str(item.get("quote") or "").split()).strip()
                text = ". ".join(part for part in [field, quote] if part).strip()
            else:
                text = " ".join(str(item or "").split()).strip()
            if not text or text in rows:
                continue
            rows.append(text[:260])
            if len(rows) >= 3:
                return rows
    return rows


def tokenize(text: str) -> set[str]:
    return {
        match.group(0).lower()
        for match in WORD_RE.finditer(str(text or ""))
        if len(match.group(0)) >= 4 and match.group(0).lower() not in STOPWORDS
    }


def collect_evidence_texts(
    *,
    request_message: str,
    executed_steps: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    report_body: str,
    sources: list[dict[str, Any]],
) -> list[str]:
    rows: list[str] = []
    if str(report_body or "").strip():
        rows.append(str(report_body).strip()[:2200])
    rows.append(" ".join(str(request_message or "").split()).strip()[:500])
    for step in executed_steps[-24:]:
        if str(step.get("status") or "").strip().lower() != "success":
            continue
        title = " ".join(str(step.get("title") or "").split()).strip()
        summary = " ".join(str(step.get("summary") or "").split()).strip()
        joined = ". ".join([item for item in [title, summary] if item]).strip()
        if joined:
            rows.append(joined[:700])
    for action in actions[-24:]:
        if str(action.get("status") or "").strip().lower() != "success":
            continue
        summary = " ".join(str(action.get("summary") or "").split()).strip()
        if summary:
            rows.append(summary[:700])
    for source in sources[:24]:
        label = " ".join(str(source.get("label") or "").split()).strip()
        url = " ".join(str(source.get("url") or "").split()).strip()
        metadata = source.get("metadata")
        excerpt = _pick_first_nonempty(
            *(metadata.get(key) for key in ("excerpt", "snippet", "text_excerpt", "description"))
        ) if isinstance(metadata, dict) else ""
        origin = infer_source_origin_label(label=label, url=url, metadata=metadata if isinstance(metadata, dict) else None)
        scope = infer_source_scope_summary(label=label, url=url, metadata=metadata if isinstance(metadata, dict) else None)
        evidence_lines = extract_source_evidence_lines(metadata if isinstance(metadata, dict) else None)
        joined = " ".join(item for item in [label, url, excerpt] if item).strip()
        if joined:
            rows.append(joined[:900])
        if origin:
            rows.append(f"Source origin: {origin}. URL: {url or 'n/a'}")
        if scope:
            rows.append(f"Scope/topic coverage: {scope}")
        for evidence_line in evidence_lines[:3]:
            rows.append(f"Source evidence: {evidence_line}")
    deduped: list[str] = []
    seen: set[str] = set()
    for row in rows:
        text = " ".join(str(row or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped[:64]


def filter_required_facts_for_coverage(
    *,
    required_facts: list[str],
    required_actions: list[str],
    delivery_target: str,
    request_message: str,
    call_json_response_fn: Callable[..., dict[str, Any]] | None = None,
) -> list[str]:
    rows = clean_text_list(required_facts, limit=6)
    if not rows:
        return []

    action_set = {str(item).strip().lower() for item in required_actions if str(item).strip()}
    normalized_delivery = " ".join(str(delivery_target or "").split()).strip().lower()

    def _fallback() -> list[str]:
        filtered: list[str] = []
        for row in rows:
            normalized_row = " ".join(str(row or "").split()).strip().lower()
            if not normalized_row:
                continue
            if normalized_delivery and normalized_delivery in normalized_row:
                continue
            if "send_email" in action_set and EMAIL_RE.search(row):
                continue
            filtered.append(row)
            if len(filtered) >= 6:
                break
        return filtered

    if not env_bool("MAIA_AGENT_LLM_FACT_SLOT_FILTER_ENABLED", default=True):
        return _fallback()
    payload = {
        "required_facts": rows,
        "required_actions": clean_text_list(required_actions, limit=6, max_item_len=64),
        "delivery_target": " ".join(str(delivery_target or "").split()).strip()[:180],
        "request_message": " ".join(str(request_message or "").split()).strip()[:420],
    }
    llm_call = call_json_response_fn or call_json_response
    try:
        response = llm_call(
            system_prompt=(
                "You classify required-fact rows for contract coverage checks. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only:\n"
                '{ "keep_indexes":[0,1], "reason":"..." }\n'
                "Rules:\n"
                "- Keep only rows that are evidence-bearing factual outcomes.\n"
                "- Remove rows that are delivery/routing/action-precondition slots.\n"
                "- Never rely on hardcoded keyword matching.\n"
                "- Use only indexes from required_facts.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=8,
            max_tokens=220,
        )
    except Exception:
        return _fallback()
    if not isinstance(response, dict):
        return _fallback()
    raw_indexes = response.get("keep_indexes")
    if not isinstance(raw_indexes, list):
        return _fallback()
    kept: list[str] = []
    for raw in raw_indexes[:12]:
        try:
            index = int(raw)
        except Exception:
            continue
        if index < 0 or index >= len(rows):
            continue
        value = rows[index]
        if value in kept:
            continue
        kept.append(value)
        if len(kept) >= 6:
            break
    return kept


def fact_missing(*, fact: str, evidence_rows: list[str]) -> bool:
    fact_tokens = tokenize(fact)
    if not fact_tokens:
        return True
    threshold = 2 if len(fact_tokens) >= 3 else 1
    for row in evidence_rows:
        overlap = len(fact_tokens.intersection(tokenize(row)))
        if overlap >= threshold:
            return False
    return True


def semantic_missing_required_facts(
    *,
    required_facts: list[str],
    evidence_rows: list[str],
    call_json_response_fn: Callable[..., dict[str, Any]] | None = None,
) -> list[str] | None:
    if not required_facts:
        return []
    if not env_bool("MAIA_AGENT_LLM_FACT_COVERAGE_CHECK_ENABLED", default=True):
        return None
    payload = {
        "required_facts": required_facts[:8],
        "evidence_rows": evidence_rows[:32],
    }
    llm_call = call_json_response_fn or call_json_response
    try:
        response = llm_call(
            system_prompt=(
                "You verify whether required facts are covered by available execution evidence. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only:\n"
                '{ "missing_fact_indexes":[0,1], "reason":"..." }\n'
                "Rules:\n"
                "- Use semantic reasoning across all evidence rows.\n"
                "- Never rely on hardcoded keyword matching.\n"
                "- Keep only indexes from required_facts that are still missing.\n"
                "- Do not invent new facts.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=320,
        )
    except Exception:
        return None
    if not isinstance(response, dict):
        return None
    raw_indexes = response.get("missing_fact_indexes")
    if not isinstance(raw_indexes, list):
        return None
    missing: list[str] = []
    for raw in raw_indexes[:12]:
        try:
            index = int(raw)
        except Exception:
            continue
        if index < 0 or index >= len(required_facts):
            continue
        fact = required_facts[index]
        if fact in missing:
            continue
        missing.append(fact)
        if len(missing) >= 8:
            break
    return missing


def successful_action_tool_ids(actions: list[dict[str, Any]]) -> set[str]:
    successful: set[str] = set()
    for action in actions[-30:]:
        if str(action.get("status") or "").strip().lower() != "success":
            continue
        tool_id = str(action.get("tool_id") or "").strip()
        if tool_id:
            successful.add(tool_id)
    return successful


def normalize_side_effect_status(value: Any) -> str:
    cleaned = " ".join(str(value or "").split()).strip().lower()
    if cleaned in {"success", "completed", "sent"}:
        return "completed"
    if cleaned in {"pending", "started", "in_progress"}:
        return "pending"
    if cleaned in {"failed", "blocked", "skipped"}:
        return cleaned
    return cleaned


def append_remediation(
    *,
    target: list[dict[str, Any]],
    tool_id: str,
    title: str,
    params: dict[str, Any] | None = None,
    allowed_tool_ids: set[str],
    max_rows: int = 4,
) -> None:
    if tool_id not in allowed_tool_ids:
        return
    payload = {
        "tool_id": tool_id,
        "title": " ".join(str(title or tool_id).split()).strip()[:120] or tool_id,
        "params": dict(params or {}),
    }
    existing = {
        (
            item.get("tool_id"),
            json.dumps(item.get("params") or {}, sort_keys=True, ensure_ascii=True),
        )
        for item in target
        if isinstance(item, dict)
    }
    if (payload["tool_id"], json.dumps(payload["params"], sort_keys=True, ensure_ascii=True)) in existing:
        return
    target.append(payload)
    if len(target) > max_rows:
        del target[max_rows:]
