from __future__ import annotations

import re
from typing import Any

from .fast_qa_outline_helpers import plan_adaptive_outline

def normalize_outline(raw_outline: dict[str, Any] | None) -> dict[str, Any]:
    fallback = {
        "style": "adaptive-detailed",
        "detail_level": "high",
        "sections": [
            {
                "title": "Answer",
                "goal": "Respond directly with evidence-grounded detail.",
                "format": "mixed",
            }
        ],
        "tone": "professional",
    }
    if not isinstance(raw_outline, dict):
        return fallback

    style = " ".join(str(raw_outline.get("style") or "").split()).strip()[:80] or fallback["style"]
    detail_level = (
        " ".join(str(raw_outline.get("detail_level") or "").split()).strip()[:40] or fallback["detail_level"]
    )
    tone = " ".join(str(raw_outline.get("tone") or "").split()).strip()[:40] or fallback["tone"]
    sections_raw = raw_outline.get("sections")
    sections: list[dict[str, str]] = []
    if isinstance(sections_raw, list):
        for row in sections_raw[:8]:
            if not isinstance(row, dict):
                continue
            title = " ".join(str(row.get("title") or "").split()).strip()[:120]
            goal = " ".join(str(row.get("goal") or "").split()).strip()[:340]
            fmt = " ".join(str(row.get("format") or "").split()).strip()[:40]
            if not title and not goal:
                continue
            sections.append(
                {
                    "title": title or "Section",
                    "goal": goal or "Explain relevant evidence-backed details.",
                    "format": fmt or "paragraphs",
                }
            )
    if not sections:
        sections = fallback["sections"]

    return {
        "style": style,
        "detail_level": detail_level,
        "sections": sections,
        "tone": tone,
    }


def apply_mindmap_focus(
    snippets: list[dict[str, Any]],
    focus: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    payload = dict(focus or {})
    if not payload or not snippets:
        return snippets

    focus_source_id = str(payload.get("source_id", "") or "").strip()
    focus_source_name = str(payload.get("source_name", "") or "").strip().lower()
    focus_page = str(payload.get("page_ref") or payload.get("page_label") or "").strip()
    focus_unit_id = str(payload.get("unit_id", "") or "").strip()
    focus_text = str(payload.get("text", "") or "").strip().lower()

    filtered = snippets
    if focus_source_id:
        filtered = [
            row
            for row in filtered
            if str(row.get("source_id", "") or "").strip() == focus_source_id
        ]
    elif focus_source_name:
        filtered = [
            row
            for row in filtered
            if focus_source_name in str(row.get("source_name", "") or "").strip().lower()
        ]
    if focus_page:
        page_filtered = [
            row for row in filtered if str(row.get("page_label", "") or "").strip() == focus_page
        ]
        if page_filtered:
            filtered = page_filtered
    if focus_unit_id:
        unit_filtered = [
            row for row in filtered if str(row.get("unit_id", "") or "").strip() == focus_unit_id
        ]
        if unit_filtered:
            filtered = unit_filtered

    if focus_text and filtered:
        focus_terms = {
            token
            for token in re.findall(r"[a-z0-9]{3,}", focus_text)
            if len(token) >= 3
        }

        def overlap_score(row: dict[str, Any]) -> int:
            text = str(row.get("text", "") or "").lower()
            return sum(1 for term in focus_terms if term in text)

        ranked = sorted(filtered, key=overlap_score, reverse=True)
        if overlap_score(ranked[0]) > 0:
            filtered = ranked[: max(4, min(10, len(ranked)))]

    return filtered or snippets


def select_relevant_snippets_with_llm(
    *,
    question: str,
    chat_history: list[list[str]],
    snippets: list[dict[str, Any]],
    max_keep: int,
    resolve_fast_qa_llm_config_fn,
    is_placeholder_api_key_fn,
    call_openai_chat_text_fn,
    parse_json_object_fn,
    logger,
) -> list[dict[str, Any]]:
    if not snippets:
        return []

    keep_limit = max(1, int(max_keep))
    candidate_window = max(keep_limit, min(len(snippets), keep_limit * 3))
    candidates = snippets[:candidate_window]

    api_key, base_url, model, _config_source = resolve_fast_qa_llm_config_fn()
    if is_placeholder_api_key_fn(api_key):
        return candidates[:keep_limit]

    history_rows: list[str] = []
    for row in chat_history[-4:]:
        if not isinstance(row, list) or len(row) < 2:
            continue
        user_text = " ".join(str(row[0] or "").split())[:280]
        assistant_text = " ".join(str(row[1] or "").split())[:280]
        if user_text or assistant_text:
            history_rows.append(f"User: {user_text}\nAssistant: {assistant_text}")
    history_text = "\n\n".join(history_rows) if history_rows else "(none)"

    candidate_rows: list[str] = []
    for idx, row in enumerate(candidates, start=1):
        source_name = " ".join(str(row.get("source_name", "Indexed file") or "").split())[:180]
        source_url = " ".join(str(row.get("source_url", "") or "").split())[:220]
        page_label = " ".join(str(row.get("page_label", "") or "").split())[:48]
        unit_id = " ".join(str(row.get("unit_id", "") or "").split())[:96]
        doc_type = " ".join(str(row.get("doc_type", "") or "").split())[:40]
        is_primary = bool(row.get("is_primary_source"))
        excerpt = " ".join(str(row.get("text", "") or "").split())[:420]
        parts = [f"[{idx}]", f"source={source_name}"]
        if source_url:
            parts.append(f"url={source_url}")
        if page_label:
            parts.append(f"page={page_label}")
        if unit_id:
            parts.append(f"unit={unit_id}")
        if doc_type:
            parts.append(f"type={doc_type}")
        parts.append(f"primary={'yes' if is_primary else 'no'}")
        parts.append(f"excerpt={excerpt}")
        candidate_rows.append(" | ".join(parts))

    prompt = (
        "Select evidence snippets that are directly relevant for answering the user question.\n"
        "Return one JSON object only with this shape:\n"
        '{"keep_ids":[1,2],"reason":"short string"}\n'
        "Rules:\n"
        "- Use both the current question and recent conversation context.\n"
        "- Keep only snippets that directly support the asked answer.\n"
        "- Remove snippets that are off-topic or implementation detail not asked by the user.\n"
        "- If a candidate is marked primary=yes, prefer it over primary=no when relevance is similar.\n"
        "- Keep non-primary snippets only as secondary context.\n"
        "- If the question includes a URL/domain and candidates do not match it, return an empty keep_ids list.\n"
        f"- Keep between 0 and {keep_limit} snippet ids.\n"
        "- IDs are 1-based and must reference only the provided candidate list.\n"
        "- Do not fabricate ids.\n\n"
        f"Question:\n{question}\n\n"
        f"Recent conversation:\n{history_text}\n\n"
        f"Candidate snippets:\n{chr(10).join(candidate_rows)}"
    )
    request_payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Maia relevance selector. "
                    "Return strict JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        raw = call_openai_chat_text_fn(
            api_key=api_key,
            base_url=base_url,
            request_payload=request_payload,
            timeout_seconds=14,
        )
        parsed = parse_json_object_fn(str(raw or ""))
        if not isinstance(parsed, dict):
            return candidates[:keep_limit]
        keep_ids_raw = parsed.get("keep_ids")
        if not isinstance(keep_ids_raw, list):
            return candidates[:keep_limit]
        keep_ids: list[int] = []
        seen: set[int] = set()
        for value in keep_ids_raw:
            try:
                parsed_id = int(str(value).strip())
            except Exception:
                continue
            if parsed_id < 1 or parsed_id > len(candidates) or parsed_id in seen:
                continue
            seen.add(parsed_id)
            keep_ids.append(parsed_id)
            if len(keep_ids) >= keep_limit:
                break
        if not keep_ids:
            return []
        return [candidates[idx - 1] for idx in keep_ids]
    except Exception:
        logger.exception("fast_qa_relevance_selector_failed")
        return candidates[:keep_limit]


def assess_evidence_sufficiency_with_llm(
    *,
    question: str,
    chat_history: list[list[str]],
    snippets: list[dict[str, Any]],
    primary_source_note: str,
    require_primary_source: bool,
    sufficiency_enabled: bool,
    sufficiency_min_confidence: float,
    resolve_fast_qa_llm_config_fn,
    is_placeholder_api_key_fn,
    call_openai_chat_text_fn,
    parse_json_object_fn,
    logger,
) -> tuple[bool, float, str]:
    if not snippets:
        return False, 0.0, "No snippets selected."
    if require_primary_source and not any(bool(row.get("is_primary_source")) for row in snippets):
        return False, 0.0, "No primary-source snippets selected."
    if not sufficiency_enabled:
        return True, 1.0, "Sufficiency check disabled."

    api_key, base_url, model, _config_source = resolve_fast_qa_llm_config_fn()
    if is_placeholder_api_key_fn(api_key):
        return True, 0.5, "Classifier unavailable."

    history_rows: list[str] = []
    for row in chat_history[-4:]:
        if not isinstance(row, list) or len(row) < 2:
            continue
        user_text = " ".join(str(row[0] or "").split())[:260]
        assistant_text = " ".join(str(row[1] or "").split())[:260]
        if user_text or assistant_text:
            history_rows.append(f"User: {user_text}\nAssistant: {assistant_text}")
    history_text = "\n\n".join(history_rows) if history_rows else "(none)"

    candidate_rows: list[str] = []
    for idx, row in enumerate(snippets[:10], start=1):
        source_name = " ".join(str(row.get("source_name", "Indexed file") or "").split())[:180]
        source_url = " ".join(str(row.get("source_url", "") or "").split())[:220]
        page_label = " ".join(str(row.get("page_label", "") or "").split())[:48]
        is_primary = bool(row.get("is_primary_source"))
        excerpt = " ".join(str(row.get("text", "") or "").split())[:520]
        parts = [f"[{idx}]", f"source={source_name}", f"primary={'yes' if is_primary else 'no'}"]
        if source_url:
            parts.append(f"url={source_url}")
        if page_label:
            parts.append(f"page={page_label}")
        parts.append(f"excerpt={excerpt}")
        candidate_rows.append(" | ".join(parts))

    prompt = (
        "Assess whether the selected evidence is sufficient to answer the latest user question professionally and specifically.\n"
        "Return one JSON object only with this shape:\n"
        '{"sufficient":true,"confidence":0.0,"reason":"short string","missing":"short string"}\n'
        "Rules:\n"
        "- sufficient=true only if the evidence contains direct support for the requested details.\n"
        "- sufficient=false when the evidence is generic and does not directly answer the asked question.\n"
        "- For follow-up questions, resolve references like 'their' from recent conversation context.\n"
        "- Avoid permissive judgments: if key details are absent, return sufficient=false.\n"
        f"- require_primary_source={'yes' if require_primary_source else 'no'}.\n"
        "- confidence must be between 0.0 and 1.0.\n\n"
        f"Question:\n{question}\n\n"
        f"Primary source guidance:\n{primary_source_note or '(none)'}\n\n"
        f"Recent conversation:\n{history_text}\n\n"
        f"Selected snippets:\n{chr(10).join(candidate_rows)}"
    )
    request_payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Maia evidence sufficiency checker. "
                    "Be strict and return JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    try:
        raw = call_openai_chat_text_fn(
            api_key=api_key,
            base_url=base_url,
            request_payload=request_payload,
            timeout_seconds=10,
        )
        parsed = parse_json_object_fn(str(raw or ""))
        if not isinstance(parsed, dict):
            return True, 0.5, "Parse failed; fail-open."
        sufficient = bool(parsed.get("sufficient"))
        try:
            confidence = float(parsed.get("confidence", 0.0) or 0.0)
        except Exception:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        reason = " ".join(str(parsed.get("reason", "") or "").split())[:220] or "No reason provided."
        threshold = max(0.05, min(0.95, float(sufficiency_min_confidence)))
        if not sufficient:
            return False, confidence, reason
        if confidence > 0.0 and confidence < (threshold * 0.75):
            return False, confidence, f"Low confidence: {reason}"
        return True, confidence, reason
    except Exception:
        logger.exception("fast_qa_evidence_sufficiency_check_failed")
        return True, 0.5, "Check failed; fail-open."


def finalize_retrieved_snippets(
    *,
    question: str,
    chat_history: list[list[str]],
    retrieved_snippets: list[dict[str, Any]],
    selected_payload: dict[str, list[Any]],
    target_urls: list[str],
    mindmap_focus: dict[str, Any] | None,
    max_keep: int,
    annotate_primary_sources_fn,
    apply_mindmap_focus_fn,
    snippet_score_fn,
    select_relevant_snippets_with_llm_fn,
    prioritize_primary_evidence_fn,
) -> tuple[list[dict[str, Any]], str, str]:
    primary_source_note = (
        f"Primary source target from user or conversation context: {', '.join(target_urls[:3])}"
        if target_urls
        else ""
    )
    if not retrieved_snippets:
        return [], primary_source_note, "no_snippets"

    # Filter out internal test/placeholder sources that should never appear in citations.
    # These are indexed during development and have no value to end users.
    _TEST_HOSTS = {"example.com", "example.org", "example.net"}
    _TEST_PARAMS = {"maia_gap_test_media", "maia_no_pdf", "maia_gap_test"}
    def _is_test_snippet(row: dict[str, Any]) -> bool:
        url = str(row.get("source_url") or row.get("page_url") or row.get("url") or "").strip().lower()
        if not url:
            return False
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            host = (parsed.netloc or "").lstrip("www.")
            if host in _TEST_HOSTS:
                return True
            qs_keys = set(parse_qs(parsed.query).keys())
            if qs_keys & _TEST_PARAMS:
                return True
        except Exception:
            pass
        return False
    retrieved_snippets = [row for row in retrieved_snippets if not _is_test_snippet(row)]
    if not retrieved_snippets:
        return [], primary_source_note, "no_snippets"

    snippets, primary_source_note = annotate_primary_sources_fn(
        question=question,
        snippets=retrieved_snippets,
        selected_payload=selected_payload,
        target_urls=target_urls,
    )
    if target_urls and not any(bool(row.get("is_primary_source")) for row in snippets):
        return [], primary_source_note, "no_primary_for_url"

    snippets = apply_mindmap_focus_fn(
        snippets,
        mindmap_focus if isinstance(mindmap_focus, dict) else {},
    )
    prioritized_pool = sorted(
        [dict(row) for row in snippets],
        key=lambda row: (
            0 if bool(row.get("is_primary_source")) else 1,
            -snippet_score_fn(row),
            str(row.get("source_name", "") or ""),
            str(row.get("page_label", "") or ""),
        ),
    )
    secondary_cap = 0 if target_urls else 2
    llm_selected = select_relevant_snippets_with_llm_fn(
        question=question,
        chat_history=chat_history,
        snippets=prioritized_pool,
        max_keep=max_keep,
    )
    if not llm_selected and any(bool(row.get("is_primary_source")) for row in prioritized_pool):
        selected = prioritize_primary_evidence_fn(
            prioritized_pool,
            max_keep=max_keep,
            max_secondary=secondary_cap,
        )
    else:
        selected = prioritize_primary_evidence_fn(
            llm_selected,
            max_keep=max_keep,
            max_secondary=secondary_cap,
        )

    if target_urls and selected and not any(bool(row.get("is_primary_source")) for row in selected):
        return [], primary_source_note, "no_primary_after_selection"
    if target_urls and not selected:
        return [], primary_source_note, "no_relevant_snippets_for_url"
    if not selected:
        return [], primary_source_note, "no_relevant_snippets"
    return selected, primary_source_note, ""

