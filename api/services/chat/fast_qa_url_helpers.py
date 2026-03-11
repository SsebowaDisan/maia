from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


def normalize_http_url(
    raw_value: Any,
    *,
    artifact_url_path_segments: set[str],
) -> str:
    value = " ".join(str(raw_value or "").split()).strip()
    if not value:
        return ""
    value = value.strip(" <>\"'`")
    value = value.rstrip(".,;:!?")
    try:
        parsed = urlparse(value)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""
    if not parsed.netloc:
        return ""
    path_segments = [
        segment.strip().lower()
        for segment in str(parsed.path or "").split("/")
        if segment.strip()
    ]
    if len(path_segments) == 1 and path_segments[0].rstrip(":") in artifact_url_path_segments:
        return ""
    normalized_path = parsed.path.rstrip("/")
    return parsed._replace(path=normalized_path, fragment="").geturl()


def normalize_host(
    raw_value: Any,
    *,
    normalize_http_url_fn,
) -> str:
    value = normalize_http_url_fn(raw_value)
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except Exception:
        return ""
    host = str(parsed.netloc or "").strip().lower()
    if not host:
        return ""
    if "@" in host:
        host = host.split("@", 1)[1]
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def host_matches(left_host: str, right_host: str) -> bool:
    if not left_host or not right_host:
        return False
    return (
        left_host == right_host
        or left_host.endswith(f".{right_host}")
        or right_host.endswith(f".{left_host}")
    )


def extract_first_url(text: str) -> str:
    match = re.search(r"https?://[^\s\])>\"']+", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).rstrip(".,;:!?")


def extract_urls(
    text: str,
    *,
    max_urls: int,
    normalize_http_url_fn,
) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for match in re.finditer(r"https?://[^\s\])>\"']+", str(text or ""), flags=re.IGNORECASE):
        value = normalize_http_url_fn(match.group(0).rstrip(".,;:!?"))
        if not value or value in seen:
            continue
        seen.add(value)
        rows.append(value)
        if len(rows) >= max(1, int(max_urls)):
            break
    return rows


def extract_urls_from_history(
    chat_history: list[list[str]],
    *,
    max_urls: int,
    extract_urls_fn,
) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for turn in reversed(chat_history[-3:]):
        if not isinstance(turn, list) or not turn:
            continue
        user_text = str(turn[0] or "")
        for value in extract_urls_fn(user_text, max_urls=max_urls):
            if not value or value in seen:
                continue
            seen.add(value)
            urls.append(value)
            if len(urls) >= max(1, int(max_urls)):
                return urls
    return urls


def resolve_contextual_url_targets(
    *,
    question: str,
    chat_history: list[list[str]],
    max_urls: int,
    extract_urls_fn,
    extract_urls_from_history_fn,
    resolve_fast_qa_llm_config_fn,
    is_placeholder_api_key_fn,
    call_openai_chat_text_fn,
    parse_json_object_fn,
    normalize_http_url_fn,
    logger,
) -> list[str]:
    explicit_targets = extract_urls_fn(question, max_urls=max_urls)
    if explicit_targets:
        return explicit_targets

    history_targets = extract_urls_from_history_fn(chat_history, max_urls=max_urls)
    if not history_targets:
        return []

    normalized_question = " ".join(str(question or "").split()).strip()
    if not normalized_question:
        return history_targets[:1]

    api_key, base_url, model, _config_source = resolve_fast_qa_llm_config_fn()
    if is_placeholder_api_key_fn(api_key):
        return history_targets[:1] if len(normalized_question) <= 220 else []

    history_rows: list[str] = []
    for row in chat_history[-2:]:
        if not isinstance(row, list) or len(row) < 2:
            continue
        user_text = " ".join(str(row[0] or "").split())[:220]
        assistant_text = " ".join(str(row[1] or "").split())[:220]
        if user_text or assistant_text:
            history_rows.append(f"User: {user_text}\nAssistant: {assistant_text}")
    history_text = "\n\n".join(history_rows) if history_rows else "(none)"

    prompt = (
        "Decide whether the latest user message should inherit website context from recent conversation.\n"
        "Return one JSON object only with this shape:\n"
        '{"inherit":true,"url":"https://example.com","reason":"short string"}\n'
        "Rules:\n"
        "- inherit=true ONLY when the latest message is a direct follow-up that explicitly names the URL's domain, a specific page from it, or a named entity that belongs exclusively to that URL.\n"
        "- inherit=false when the latest message could equally refer to an uploaded file, a different document, or any other context.\n"
        "- inherit=false when the latest message is a new topic, a different task, or does not mention the prior URL or its domain.\n"
        "- When in doubt, set inherit=false — never carry over URL context speculatively.\n"
        "- If inherit=true, url must be one of the candidate URLs provided.\n"
        "- Prefer the most recent relevant candidate URL.\n\n"
        f"Latest user message:\n{normalized_question}\n\n"
        f"Recent conversation (last 2 turns only):\n{history_text}\n\n"
        f"Candidate URLs:\n{chr(10).join(history_targets[:3])}"
    )
    request_payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Maia URL-context resolver. "
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
            timeout_seconds=8,
        )
        parsed = parse_json_object_fn(str(raw or ""))
        if not isinstance(parsed, dict):
            return history_targets[:1]
        inherit = bool(parsed.get("inherit"))
        if not inherit:
            return []
        requested_url = normalize_http_url_fn(parsed.get("url"))
        if requested_url and requested_url in history_targets:
            return [requested_url]
        return history_targets[:1]
    except Exception:
        logger.exception("fast_qa_url_context_resolution_failed")
        return []


def rewrite_followup_question_for_retrieval(
    *,
    question: str,
    chat_history: list[list[str]],
    target_urls: list[str] | None,
    normalize_http_url_fn,
    extract_urls_fn,
    resolve_fast_qa_llm_config_fn,
    is_placeholder_api_key_fn,
    call_openai_chat_text_fn,
    parse_json_object_fn,
    logger,
) -> tuple[str, bool, str]:
    normalized_question = " ".join(str(question or "").split()).strip()
    if not normalized_question:
        return "", False, "empty-question"
    urls = [value for value in (target_urls or []) if normalize_http_url_fn(value)]
    if not chat_history:
        return normalized_question, False, "no-history"

    api_key, base_url, model, _config_source = resolve_fast_qa_llm_config_fn()
    if is_placeholder_api_key_fn(api_key):
        return normalized_question, False, "llm-unavailable"

    history_rows: list[str] = []
    for row in chat_history[-3:]:
        if not isinstance(row, list) or len(row) < 2:
            continue
        user_text = " ".join(str(row[0] or "").split())[:260]
        assistant_text = " ".join(str(row[1] or "").split())[:260]
        if user_text or assistant_text:
            history_rows.append(f"User: {user_text}\nAssistant: {assistant_text}")
    history_text = "\n\n".join(history_rows) if history_rows else "(none)"

    prompt = (
        "Rewrite the latest user message into a standalone retrieval query for evidence search.\n"
        "Return one JSON object only with this shape:\n"
        '{"standalone_query":"string","is_follow_up":true,"reason":"short string"}\n'
        "Rules:\n"
        "- Resolve pronouns and context dependencies using recent conversation.\n"
        "- Keep the query faithful to the user's intent; do not add unsupported assumptions.\n"
        "- If a primary URL context exists, keep that URL/domain in the query.\n"
        "- Keep query concise and retrieval-oriented.\n\n"
        f"Latest user message:\n{normalized_question}\n\n"
        f"Recent conversation:\n{history_text}\n\n"
        f"Primary URL context:\n{', '.join(urls[:3]) or '(none)'}"
    )
    request_payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Maia retrieval-query rewriter. "
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
            timeout_seconds=10,
        )
        parsed = parse_json_object_fn(str(raw or ""))
        if not isinstance(parsed, dict):
            rewritten = normalized_question
            if urls and not extract_urls_fn(rewritten, max_urls=2):
                rewritten = f"{rewritten} {urls[0]}"
            return rewritten, bool(urls), "parse-failed"

        rewritten = " ".join(str(parsed.get("standalone_query") or "").split()).strip()
        if not rewritten:
            rewritten = normalized_question
        is_follow_up = bool(parsed.get("is_follow_up"))
        reason = " ".join(str(parsed.get("reason") or "").split()).strip()[:180] or "ok"

        if len(rewritten) > 480:
            rewritten = rewritten[:480].rsplit(" ", 1)[0].strip()
        # Only append URL context when the LLM confirmed this is a follow-up on that URL
        if is_follow_up and urls and not extract_urls_fn(rewritten, max_urls=2):
            rewritten = f"{rewritten} {urls[0]}".strip()
        return rewritten, is_follow_up, reason
    except Exception:
        logger.exception("fast_qa_followup_query_rewrite_failed")
        return normalized_question, False, "rewrite-failed"


def expand_retrieval_query_for_gap(
    *,
    question: str,
    current_query: str,
    chat_history: list[list[str]],
    snippets: list[dict[str, Any]],
    insufficiency_reason: str,
    target_urls: list[str] | None,
    normalize_http_url_fn,
    extract_urls_fn,
    resolve_fast_qa_llm_config_fn,
    is_placeholder_api_key_fn,
    call_openai_chat_text_fn,
    parse_json_object_fn,
    logger,
) -> tuple[str, str]:
    normalized_question = " ".join(str(question or "").split()).strip()
    normalized_current = " ".join(str(current_query or "").split()).strip()
    if not normalized_current:
        normalized_current = normalized_question
    urls = [value for value in (target_urls or []) if normalize_http_url_fn(value)]
    if not normalized_current:
        return "", "empty-query"

    api_key, base_url, model, _config_source = resolve_fast_qa_llm_config_fn()
    if is_placeholder_api_key_fn(api_key):
        return normalized_current, "llm-unavailable"

    history_rows: list[str] = []
    for row in chat_history[-3:]:
        if not isinstance(row, list) or len(row) < 2:
            continue
        user_text = " ".join(str(row[0] or "").split())[:220]
        assistant_text = " ".join(str(row[1] or "").split())[:220]
        if user_text or assistant_text:
            history_rows.append(f"User: {user_text}\nAssistant: {assistant_text}")
    history_text = "\n\n".join(history_rows) if history_rows else "(none)"

    evidence_rows: list[str] = []
    for idx, row in enumerate(snippets[:8], start=1):
        source_name = " ".join(str(row.get("source_name", "Indexed file") or "").split())[:180]
        source_url = " ".join(str(row.get("source_url", "") or "").split())[:220]
        excerpt = " ".join(str(row.get("text", "") or "").split())[:360]
        is_primary = bool(row.get("is_primary_source"))
        parts = [f"[{idx}]", f"source={source_name}", f"primary={'yes' if is_primary else 'no'}"]
        if source_url:
            parts.append(f"url={source_url}")
        parts.append(f"excerpt={excerpt}")
        evidence_rows.append(" | ".join(parts))
    evidence_text = "\n".join(evidence_rows) if evidence_rows else "(none)"

    prompt = (
        "Generate an improved retrieval query for a follow-up evidence search.\n"
        "Return one JSON object only with this shape:\n"
        '{"expanded_query":"string","reason":"short string"}\n'
        "Rules:\n"
        "- Keep intent identical to the user question.\n"
        "- Resolve follow-up references using chat history.\n"
        "- Include concrete entities and details needed to fill missing evidence gaps.\n"
        "- Preserve primary URL/domain context when provided.\n"
        "- Keep query concise and retrieval-oriented.\n"
        "- Do not fabricate facts.\n\n"
        f"User question:\n{normalized_question}\n\n"
        f"Current retrieval query:\n{normalized_current}\n\n"
        f"Evidence insufficiency reason:\n{insufficiency_reason or '(none)'}\n\n"
        f"Recent conversation:\n{history_text}\n\n"
        f"Primary URL context:\n{', '.join(urls[:3]) or '(none)'}\n\n"
        f"Current snippets:\n{evidence_text}"
    )
    request_payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Maia retrieval-query optimizer. "
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
            timeout_seconds=10,
        )
        parsed = parse_json_object_fn(str(raw or ""))
        if not isinstance(parsed, dict):
            expanded = normalized_current
            if urls and not extract_urls_fn(expanded, max_urls=2):
                expanded = f"{expanded} {urls[0]}".strip()
            return expanded, "parse-failed"

        expanded = " ".join(str(parsed.get("expanded_query") or "").split()).strip()
        if not expanded:
            expanded = normalized_current
        if len(expanded) > 480:
            expanded = expanded[:480].rsplit(" ", 1)[0].strip()
        # Only append URL context when it was already present in the current query
        if urls and not extract_urls_fn(expanded, max_urls=2) and extract_urls_fn(normalized_current, max_urls=2):
            expanded = f"{expanded} {urls[0]}".strip()
        reason = " ".join(str(parsed.get("reason") or "").split()).strip()[:180] or "ok"
        return expanded, reason
    except Exception:
        logger.exception("fast_qa_retrieval_query_expansion_failed")
        return normalized_current, "expand-failed"
