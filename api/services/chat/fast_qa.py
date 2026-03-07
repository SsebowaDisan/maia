from __future__ import annotations

from copy import deepcopy
import json
import logging
import re
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from decouple import config
from fastapi import HTTPException

from ktem.llms.manager import llms
from ktem.pages.chat.common import STATE
from maia.mindmap.indexer import build_knowledge_map

from api.context import ApiContext
from api.schemas import ChatRequest

from .citations import (
    assign_fast_source_refs,
    build_citation_quality_metrics,
    build_claim_signal_summary,
    build_source_usage,
    build_fast_info_html,
    enforce_required_citations,
    normalize_fast_answer,
    render_fast_citation_links,
    resolve_required_citation_mode,
)
from .constants import (
    API_FAST_QA_MAX_IMAGES,
    API_FAST_QA_MAX_SNIPPETS,
    API_FAST_QA_MAX_SOURCES,
    API_FAST_QA_SOURCE_SCAN,
    API_FAST_QA_TEMPERATURE,
    MAIA_CITATION_STRENGTH_ORDERING_ENABLED,
    MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD,
    MAIA_SOURCE_USAGE_HEATMAP_ENABLED,
    DEFAULT_SETTING,
)
from .conversation_store import (
    build_selected_payload,
    get_or_create_conversation,
    maybe_autoname_conversation,
    persist_conversation,
)
from .fast_qa_retrieval import load_recent_chunks_for_fast_qa
from .info_panel_copy import build_info_panel_copy
from .language import (
    build_response_language_rule,
    resolve_response_language,
)
from .pipeline import is_placeholder_api_key

logger = logging.getLogger(__name__)
_ARTIFACT_URL_PATH_SEGMENTS = {
    "extract",
    "source",
    "link",
    "evidence",
    "citation",
    "title",
    "markdown",
    "content",
    "published",
    "time",
    "url",
}
MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_ENABLED = bool(
    config("MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_ENABLED", default=True, cast=bool)
)
MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_MIN_CONFIDENCE = float(
    config("MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_MIN_CONFIDENCE", default=0.58, cast=float)
)


def _normalize_request_attachments(request: ChatRequest) -> list[dict[str, str]]:
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


def _extract_text_content(raw_content: Any) -> str:
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


def _call_openai_chat_text(
    *,
    api_key: str,
    base_url: str,
    request_payload: dict[str, Any],
    timeout_seconds: int = 20,
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
    return _extract_text_content(message.get("content")) or None


def _parse_json_object(raw_text: str) -> dict[str, Any] | None:
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


def _truncate_for_log(value: Any, limit: int = 1600) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(+{len(text) - limit} chars)"


def _extract_first_url(text: str) -> str:
    match = re.search(r"https?://[^\s\])>\"']+", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).rstrip(".,;:!?")


def _extract_urls(text: str, *, max_urls: int = 6) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for match in re.finditer(r"https?://[^\s\])>\"']+", str(text or ""), flags=re.IGNORECASE):
        value = _normalize_http_url(match.group(0).rstrip(".,;:!?"))
        if not value or value in seen:
            continue
        seen.add(value)
        rows.append(value)
        if len(rows) >= max(1, int(max_urls)):
            break
    return rows


def _extract_urls_from_history(
    chat_history: list[list[str]],
    *,
    max_urls: int = 6,
) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for turn in reversed(chat_history[-8:]):
        if not isinstance(turn, list) or not turn:
            continue
        user_text = str(turn[0] or "")
        for value in _extract_urls(user_text, max_urls=max_urls):
            if not value or value in seen:
                continue
            seen.add(value)
            urls.append(value)
            if len(urls) >= max(1, int(max_urls)):
                return urls
    return urls


def _resolve_contextual_url_targets(
    *,
    question: str,
    chat_history: list[list[str]],
    max_urls: int = 6,
) -> list[str]:
    explicit_targets = _extract_urls(question, max_urls=max_urls)
    if explicit_targets:
        return explicit_targets

    history_targets = _extract_urls_from_history(chat_history, max_urls=max_urls)
    if not history_targets:
        return []

    normalized_question = " ".join(str(question or "").split()).strip()
    if not normalized_question:
        return history_targets[:1]

    api_key, base_url, model, _config_source = _resolve_fast_qa_llm_config()
    if is_placeholder_api_key(api_key):
        # Fallback heuristic when classifier LLM is unavailable.
        return history_targets[:1] if len(normalized_question) <= 220 else []

    history_rows: list[str] = []
    for row in chat_history[-4:]:
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
        "- inherit=true only when the latest message is a follow-up that depends on prior website context.\n"
        "- inherit=false when the latest message is a new topic unrelated to previous URLs.\n"
        "- If inherit=true, url must be one of the candidate URLs provided.\n"
        "- Prefer the most recent relevant candidate URL.\n\n"
        f"Latest user message:\n{normalized_question}\n\n"
        f"Recent conversation:\n{history_text}\n\n"
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
        raw = _call_openai_chat_text(
            api_key=api_key,
            base_url=base_url,
            request_payload=request_payload,
            timeout_seconds=8,
        )
        parsed = _parse_json_object(str(raw or ""))
        if not isinstance(parsed, dict):
            return history_targets[:1]
        inherit = bool(parsed.get("inherit"))
        if not inherit:
            return []
        requested_url = _normalize_http_url(parsed.get("url"))
        if requested_url and requested_url in history_targets:
            return [requested_url]
        return history_targets[:1]
    except Exception:
        logger.exception("fast_qa_url_context_resolution_failed")
        return history_targets[:1] if len(normalized_question) <= 220 else []


def _rewrite_followup_question_for_retrieval(
    *,
    question: str,
    chat_history: list[list[str]],
    target_urls: list[str] | None = None,
) -> tuple[str, bool, str]:
    normalized_question = " ".join(str(question or "").split()).strip()
    if not normalized_question:
        return "", False, "empty-question"
    urls = [value for value in (target_urls or []) if _normalize_http_url(value)]
    if not chat_history:
        if urls and not _extract_urls(normalized_question, max_urls=2):
            return f"{normalized_question} {urls[0]}", False, "no-history-appended-url-context"
        return normalized_question, False, "no-history"

    api_key, base_url, model, _config_source = _resolve_fast_qa_llm_config()
    if is_placeholder_api_key(api_key):
        if urls and not _extract_urls(normalized_question, max_urls=2):
            return f"{normalized_question} {urls[0]}", True, "llm-unavailable-appended-url-context"
        return normalized_question, True, "llm-unavailable"

    history_rows: list[str] = []
    for row in chat_history[-6:]:
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
        raw = _call_openai_chat_text(
            api_key=api_key,
            base_url=base_url,
            request_payload=request_payload,
            timeout_seconds=10,
        )
        parsed = _parse_json_object(str(raw or ""))
        if not isinstance(parsed, dict):
            rewritten = normalized_question
            if urls and not _extract_urls(rewritten, max_urls=2):
                rewritten = f"{rewritten} {urls[0]}"
            return rewritten, bool(urls), "parse-failed"

        rewritten = " ".join(str(parsed.get("standalone_query") or "").split()).strip()
        if not rewritten:
            rewritten = normalized_question
        is_follow_up = bool(parsed.get("is_follow_up"))
        reason = " ".join(str(parsed.get("reason") or "").split()).strip()[:180] or "ok"

        if len(rewritten) > 480:
            rewritten = rewritten[:480].rsplit(" ", 1)[0].strip()
        if urls and not _extract_urls(rewritten, max_urls=2):
            rewritten = f"{rewritten} {urls[0]}".strip()
        return rewritten, is_follow_up or bool(urls), reason
    except Exception:
        logger.exception("fast_qa_followup_query_rewrite_failed")
        fallback = normalized_question
        if urls and not _extract_urls(fallback, max_urls=2):
            fallback = f"{fallback} {urls[0]}"
        return fallback, bool(urls), "rewrite-failed"


def _expand_retrieval_query_for_gap(
    *,
    question: str,
    current_query: str,
    chat_history: list[list[str]],
    snippets: list[dict[str, Any]],
    insufficiency_reason: str,
    target_urls: list[str] | None = None,
) -> tuple[str, str]:
    normalized_question = " ".join(str(question or "").split()).strip()
    normalized_current = " ".join(str(current_query or "").split()).strip()
    if not normalized_current:
        normalized_current = normalized_question
    urls = [value for value in (target_urls or []) if _normalize_http_url(value)]
    if not normalized_current:
        return "", "empty-query"

    api_key, base_url, model, _config_source = _resolve_fast_qa_llm_config()
    if is_placeholder_api_key(api_key):
        if urls and not _extract_urls(normalized_current, max_urls=2):
            return f"{normalized_current} {urls[0]}", "llm-unavailable-appended-url-context"
        return normalized_current, "llm-unavailable"

    history_rows: list[str] = []
    for row in chat_history[-6:]:
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
        raw = _call_openai_chat_text(
            api_key=api_key,
            base_url=base_url,
            request_payload=request_payload,
            timeout_seconds=10,
        )
        parsed = _parse_json_object(str(raw or ""))
        if not isinstance(parsed, dict):
            expanded = normalized_current
            if urls and not _extract_urls(expanded, max_urls=2):
                expanded = f"{expanded} {urls[0]}".strip()
            return expanded, "parse-failed"

        expanded = " ".join(str(parsed.get("expanded_query") or "").split()).strip()
        if not expanded:
            expanded = normalized_current
        if len(expanded) > 480:
            expanded = expanded[:480].rsplit(" ", 1)[0].strip()
        if urls and not _extract_urls(expanded, max_urls=2):
            expanded = f"{expanded} {urls[0]}".strip()
        reason = " ".join(str(parsed.get("reason") or "").split()).strip()[:180] or "ok"
        return expanded, reason
    except Exception:
        logger.exception("fast_qa_retrieval_query_expansion_failed")
        fallback = normalized_current
        if urls and not _extract_urls(fallback, max_urls=2):
            fallback = f"{fallback} {urls[0]}".strip()
        return fallback, "expand-failed"


def _normalize_http_url(raw_value: Any) -> str:
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
    if len(path_segments) == 1 and path_segments[0].rstrip(":") in _ARTIFACT_URL_PATH_SEGMENTS:
        return ""
    normalized_path = parsed.path.rstrip("/")
    return parsed._replace(path=normalized_path, fragment="").geturl()


def _normalize_host(raw_value: Any) -> str:
    value = _normalize_http_url(raw_value)
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


def _host_matches(left_host: str, right_host: str) -> bool:
    if not left_host or not right_host:
        return False
    return (
        left_host == right_host
        or left_host.endswith(f".{right_host}")
        or right_host.endswith(f".{left_host}")
    )


def _selected_source_ids(selected_payload: dict[str, list[Any]]) -> set[str]:
    ids: set[str] = set()
    for value in (selected_payload or {}).values():
        if not isinstance(value, list) or len(value) < 2:
            continue
        mode = str(value[0] or "").strip().lower()
        if mode != "select":
            continue
        file_ids = value[1] if isinstance(value[1], list) else []
        for file_id in file_ids:
            normalized = str(file_id or "").strip()
            if normalized:
                ids.add(normalized)
    return ids


def _snippet_score(row: dict[str, Any]) -> float:
    try:
        return float(row.get("score", 0.0) or 0.0)
    except Exception:
        return 0.0


def _annotate_primary_sources(
    *,
    question: str,
    snippets: list[dict[str, Any]],
    selected_payload: dict[str, list[Any]],
    target_urls: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    if not snippets:
        return [], ""

    selected_ids = _selected_source_ids(selected_payload)
    resolved_target_urls = (
        [value for value in (target_urls or []) if _normalize_http_url(value)]
        or _extract_urls(question, max_urls=6)
    )
    has_url_targets = bool(resolved_target_urls)
    target_url_set = {value for value in resolved_target_urls if value}
    target_hosts = {
        _normalize_host(value)
        for value in resolved_target_urls
        if _normalize_host(value)
    }
    target_paths = {
        str(urlparse(value).path or "").strip().lower()
        for value in resolved_target_urls
        if value
    }

    annotated: list[dict[str, Any]] = []
    primary_count = 0
    for row in snippets:
        item = dict(row)
        source_id = str(item.get("source_id", "") or "").strip()
        source_url = _normalize_http_url(
            item.get("source_url")
            or item.get("page_url")
            or item.get("url")
            or item.get("source_name")
        )
        source_host = _normalize_host(source_url)
        source_path = str(urlparse(source_url).path or "").strip().lower() if source_url else ""

        exact_url_match = bool(source_url and source_url in target_url_set)
        path_match = bool(source_path and source_path in target_paths and source_path not in {"", "/"})
        host_match = bool(
            source_host
            and target_hosts
            and any(_host_matches(source_host, host) for host in target_hosts)
        )
        selected_match = bool(source_id and source_id in selected_ids)

        if has_url_targets:
            # For URL-targeted prompts, treat URL/domain/path matches as primary;
            # prior user-selected files should not override URL grounding.
            is_primary = exact_url_match or path_match or host_match
        else:
            is_primary = selected_match or exact_url_match or path_match or host_match
        item["source_url"] = source_url
        item["is_primary_source"] = bool(is_primary)
        if is_primary:
            primary_count += 1
            item["score"] = _snippet_score(item) + 80.0
        annotated.append(item)

    if primary_count <= 0:
        return annotated, ""

    sort_rows = sorted(
        annotated,
        key=lambda row: (
            0 if bool(row.get("is_primary_source")) else 1,
            -_snippet_score(row),
            str(row.get("source_name", "") or ""),
            str(row.get("page_label", "") or ""),
        ),
    )
    if resolved_target_urls:
        primary_note = f"Primary source target from user or conversation context: {', '.join(resolved_target_urls[:3])}"
    elif selected_ids:
        primary_note = (
            "Primary source target from user-selected file(s): "
            f"{', '.join(sorted(selected_ids)[:3])}"
        )
    else:
        primary_note = "Primary source target inferred from user-provided sources."
    return sort_rows, primary_note


def _prioritize_primary_evidence(
    snippets: list[dict[str, Any]],
    *,
    max_keep: int,
    max_secondary: int = 2,
) -> list[dict[str, Any]]:
    if not snippets:
        return []
    keep_limit = max(1, int(max_keep))
    ordered = sorted(
        [dict(row) for row in snippets],
        key=lambda row: (
            0 if bool(row.get("is_primary_source")) else 1,
            -_snippet_score(row),
            str(row.get("source_name", "") or ""),
            str(row.get("page_label", "") or ""),
        ),
    )
    primary_rows = [row for row in ordered if bool(row.get("is_primary_source"))]
    secondary_rows = [row for row in ordered if not bool(row.get("is_primary_source"))]
    if not primary_rows:
        return ordered[:keep_limit]

    keep_secondary = min(max(0, int(max_secondary)), max(0, keep_limit - 1))
    result: list[dict[str, Any]] = []
    result.extend(primary_rows[:keep_limit])
    if len(result) < keep_limit:
        remaining_slots = min(keep_limit - len(result), keep_secondary)
        result.extend(secondary_rows[:remaining_slots])
    return result[:keep_limit]


def _build_no_relevant_evidence_answer(
    question: str,
    *,
    target_url: str = "",
    response_language: str | None = None,
) -> str:
    normalized_language = " ".join(str(response_language or "").split()).strip().lower()
    localized: dict[str, tuple[str, str]] = {
        "es": (
            "No pude encontrar evidencia indexada para {url} en este contexto del proyecto. "
            "No es visible en el contenido indexado. Si lo necesitas, ejecuta el indexado del sitio web o una busqueda en linea para esa URL y vuelve a preguntar.",
            "No pude encontrar evidencia relevante en los archivos indexados del proyecto ni en el contexto reciente de la conversacion para esta pregunta. "
            "No es visible en el contenido indexado.",
        ),
        "fr": (
            "Je n'ai pas trouve de preuves indexees pour {url} dans ce contexte de projet. "
            "Ce n'est pas visible dans le contenu indexe. Si besoin, lancez l'indexation du site web ou une recherche en ligne pour cette URL, puis reposez la question.",
            "Je n'ai pas trouve de preuves pertinentes dans les fichiers de projet indexes ni dans le contexte recent de la conversation pour cette question. "
            "Ce n'est pas visible dans le contenu indexe.",
        ),
        "de": (
            "Ich konnte in diesem Projektkontext keine indexierten Belege fuer {url} finden. "
            "Im indexierten Inhalt nicht sichtbar. Falls noetig, starten Sie die Website-Indexierung oder eine Online-Suche fuer diese URL und fragen Sie dann erneut.",
            "Ich konnte in den indexierten Projektdateien und im aktuellen Gespraechskontext keine relevanten Belege fuer diese Frage finden. "
            "Im indexierten Inhalt nicht sichtbar.",
        ),
        "it": (
            "Non ho trovato evidenze indicizzate per {url} in questo contesto di progetto. "
            "Non visibile nei contenuti indicizzati. Se necessario, esegui l'indicizzazione del sito web o una ricerca online per quell'URL e chiedi di nuovo.",
            "Non ho trovato evidenze rilevanti nei file di progetto indicizzati e nel contesto recente della conversazione per questa domanda. "
            "Non visibile nei contenuti indicizzati.",
        ),
        "pt": (
            "Nao encontrei evidencia indexada para {url} neste contexto do projeto. "
            "Nao esta visivel no conteudo indexado. Se necessario, execute a indexacao do site ou uma pesquisa online para essa URL e pergunte novamente.",
            "Nao encontrei evidencia relevante nos arquivos indexados do projeto nem no contexto recente da conversa para esta pergunta. "
            "Nao esta visivel no conteudo indexado.",
        ),
        "nl": (
            "Ik kon geen geindexeerd bewijs voor {url} vinden in deze projectcontext. "
            "Niet zichtbaar in geindexeerde inhoud. Start zo nodig website-indexering of online zoeken voor die URL en vraag het daarna opnieuw.",
            "Ik kon geen relevant bewijs vinden in geindexeerde projectbestanden en recente gesprekscontext voor deze vraag. "
            "Niet zichtbaar in geindexeerde inhoud.",
        ),
    }
    resolved_target_url = _normalize_http_url(target_url) or _extract_first_url(question)
    localized_pair = localized.get(normalized_language)
    if resolved_target_url:
        if localized_pair:
            return localized_pair[0].format(url=resolved_target_url)
        return (
            f"I could not find indexed evidence for {resolved_target_url} in this project context. "
            "Not visible in indexed content. If needed, run website indexing or online search for that URL, then ask again."
        )
    if localized_pair:
        return localized_pair[1]
    return (
        "I could not find relevant evidence in indexed project files and recent conversation context for this question. "
        "Not visible in indexed content."
    )


def _resolve_fast_qa_llm_config() -> tuple[str, str, str, str]:
    default_base = str(config("OPENAI_API_BASE", default="https://api.openai.com/v1")) or "https://api.openai.com/v1"
    default_model = str(config("OPENAI_CHAT_MODEL", default="gpt-4o-mini")) or "gpt-4o-mini"
    env_api_key = str(config("OPENAI_API_KEY", default="") or "").strip()
    if not is_placeholder_api_key(env_api_key):
        return env_api_key, default_base, default_model, "env"

    try:
        default_name = str(llms.get_default_name() or "").strip()
    except Exception:
        default_name = ""
    try:
        model_info = llms.info().get(default_name, {}) if default_name else {}
    except Exception:
        model_info = {}
    spec = model_info.get("spec", {}) if isinstance(model_info, dict) else {}
    if not isinstance(spec, dict):
        spec = {}

    spec_api_key = str(spec.get("api_key") or "").strip()
    spec_base_url = (
        str(spec.get("base_url") or spec.get("openai_api_base") or spec.get("api_base") or "").strip()
    )
    spec_model = str(spec.get("model") or spec.get("model_name") or "").strip()
    if not is_placeholder_api_key(spec_api_key):
        resolved_model = spec_model or default_model
        resolved_base_url = spec_base_url or default_base
        return spec_api_key, resolved_base_url, resolved_model, f"llm:{default_name or 'default'}"

    return "", default_base, default_model, "missing"


def _normalize_outline(raw_outline: dict[str, Any] | None) -> dict[str, Any]:
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
        for row in sections_raw[:6]:
            if not isinstance(row, dict):
                continue
            title = " ".join(str(row.get("title") or "").split()).strip()[:120]
            goal = " ".join(str(row.get("goal") or "").split()).strip()[:220]
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


def _apply_mindmap_focus(
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


def _select_relevant_snippets_with_llm(
    *,
    question: str,
    chat_history: list[list[str]],
    snippets: list[dict[str, Any]],
    max_keep: int,
) -> list[dict[str, Any]]:
    if not snippets:
        return []

    keep_limit = max(1, int(max_keep))
    candidate_window = max(keep_limit, min(len(snippets), keep_limit * 3))
    candidates = snippets[:candidate_window]

    api_key, base_url, model, _config_source = _resolve_fast_qa_llm_config()
    if is_placeholder_api_key(api_key):
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
        raw = _call_openai_chat_text(
            api_key=api_key,
            base_url=base_url,
            request_payload=request_payload,
            timeout_seconds=14,
        )
        parsed = _parse_json_object(str(raw or ""))
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


def _assess_evidence_sufficiency_with_llm(
    *,
    question: str,
    chat_history: list[list[str]],
    snippets: list[dict[str, Any]],
    primary_source_note: str = "",
    require_primary_source: bool = False,
) -> tuple[bool, float, str]:
    if not snippets:
        return False, 0.0, "No snippets selected."
    if require_primary_source and not any(bool(row.get("is_primary_source")) for row in snippets):
        return False, 0.0, "No primary-source snippets selected."
    if not MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_ENABLED:
        return True, 1.0, "Sufficiency check disabled."

    api_key, base_url, model, _config_source = _resolve_fast_qa_llm_config()
    if is_placeholder_api_key(api_key):
        # Fail open when classifier LLM is unavailable.
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
        raw = _call_openai_chat_text(
            api_key=api_key,
            base_url=base_url,
            request_payload=request_payload,
            timeout_seconds=10,
        )
        parsed = _parse_json_object(str(raw or ""))
        if not isinstance(parsed, dict):
            return True, 0.5, "Parse failed; fail-open."
        sufficient = bool(parsed.get("sufficient"))
        try:
            confidence = float(parsed.get("confidence", 0.0) or 0.0)
        except Exception:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        reason = " ".join(str(parsed.get("reason", "") or "").split())[:220] or "No reason provided."
        threshold = max(
            0.05,
            min(0.95, float(MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_MIN_CONFIDENCE)),
        )
        if not sufficient:
            return False, confidence, reason
        if confidence > 0.0 and confidence < (threshold * 0.75):
            return False, confidence, f"Low confidence: {reason}"
        return True, confidence, reason
    except Exception:
        logger.exception("fast_qa_evidence_sufficiency_check_failed")
        return True, 0.5, "Check failed; fail-open."


def _finalize_retrieved_snippets(
    *,
    question: str,
    chat_history: list[list[str]],
    retrieved_snippets: list[dict[str, Any]],
    selected_payload: dict[str, list[Any]],
    target_urls: list[str],
    mindmap_focus: dict[str, Any] | None,
    max_keep: int,
) -> tuple[list[dict[str, Any]], str, str]:
    primary_source_note = (
        f"Primary source target from user or conversation context: {', '.join(target_urls[:3])}"
        if target_urls
        else ""
    )
    if not retrieved_snippets:
        return [], primary_source_note, "no_snippets"

    snippets, primary_source_note = _annotate_primary_sources(
        question=question,
        snippets=retrieved_snippets,
        selected_payload=selected_payload,
        target_urls=target_urls,
    )
    if target_urls and not any(bool(row.get("is_primary_source")) for row in snippets):
        return [], primary_source_note, "no_primary_for_url"

    snippets = _apply_mindmap_focus(
        snippets,
        mindmap_focus if isinstance(mindmap_focus, dict) else {},
    )
    prioritized_pool = sorted(
        [dict(row) for row in snippets],
        key=lambda row: (
            0 if bool(row.get("is_primary_source")) else 1,
            -_snippet_score(row),
            str(row.get("source_name", "") or ""),
            str(row.get("page_label", "") or ""),
        ),
    )
    secondary_cap = 0 if target_urls else 2
    llm_selected = _select_relevant_snippets_with_llm(
        question=question,
        chat_history=chat_history,
        snippets=prioritized_pool,
        max_keep=max_keep,
    )
    if not llm_selected and any(bool(row.get("is_primary_source")) for row in prioritized_pool):
        selected = _prioritize_primary_evidence(
            prioritized_pool,
            max_keep=max_keep,
            max_secondary=secondary_cap,
        )
    else:
        selected = _prioritize_primary_evidence(
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


def _plan_adaptive_outline(
    *,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    question: str,
    history_text: str,
    refs_text: str,
    context_text: str,
) -> dict[str, Any]:
    planner_temperature = max(0.0, min(1.0, float(temperature) * 0.5))
    refs_count = len(re.findall(r"^\[\d+\]\s", refs_text or "", flags=re.MULTILINE))
    logger.warning(
        "fast_qa_planner_request model=%s temp=%.3f refs=%d history_chars=%d context_chars=%d question=%s",
        model,
        planner_temperature,
        refs_count,
        len(history_text or ""),
        len(context_text or ""),
        _truncate_for_log(question, 280),
    )
    planner_prompt = (
        "Create an answer blueprint for a retrieval-grounded assistant reply.\n"
        "Return one JSON object only with keys:\n"
        '{ "style": "string", "detail_level": "high", "sections": [{"title":"string","goal":"string","format":"paragraphs|bullets|table|mixed"}], "tone": "string" }\n'
        "Rules:\n"
        "- Structure must be specific to this exact user request and evidence, not a generic reusable template.\n"
        "- Match detail level to user intent; direct questions should stay focused and concise.\n"
        "- Use 1-6 sections.\n"
        "- Section titles must be specific, professional, and tied to concrete entities in the request/evidence.\n"
        "- Do not default to reusable company-profile or marketing-report skeletons unless explicitly requested.\n"
        "- If user intent is unclear/noisy, produce one section focused on a clarifying question instead of assumptions.\n"
        "- Do not invent facts.\n\n"
        f"Question:\n{question}\n\n"
        f"Recent chat history:\n{history_text}\n\n"
        f"Source index:\n{refs_text or '(none)'}\n\n"
        f"Evidence excerpt (truncated):\n{context_text[:6000]}"
    )
    planner_payload = {
        "model": model,
        "temperature": planner_temperature,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You design response structures for professional assistants. "
                    "Return JSON only."
                ),
            },
            {"role": "user", "content": planner_prompt},
        ],
    }
    try:
        planned_raw = _call_openai_chat_text(
            api_key=api_key,
            base_url=base_url,
            request_payload=planner_payload,
            timeout_seconds=16,
        )
        parsed_outline = _parse_json_object(str(planned_raw or ""))
        normalized_outline = _normalize_outline(parsed_outline)
        logger.warning(
            "fast_qa_planner_output parse_ok=%s sections=%d style=%s raw=%s parsed=%s normalized=%s",
            bool(parsed_outline),
            len(normalized_outline.get("sections", []) or []),
            str(normalized_outline.get("style", "")),
            _truncate_for_log(planned_raw, 900),
            _truncate_for_log(
                json.dumps(parsed_outline, ensure_ascii=True, separators=(",", ":"))
                if parsed_outline
                else "(parse-failed)",
                900,
            ),
            _truncate_for_log(
                json.dumps(normalized_outline, ensure_ascii=True, separators=(",", ":")),
                900,
            ),
        )
        return normalized_outline
    except Exception:
        logger.exception("fast_qa_planner_output error; using fallback outline")
        fallback_outline = _normalize_outline(None)
        logger.warning(
            "fast_qa_planner_fallback normalized=%s",
            _truncate_for_log(
                json.dumps(fallback_outline, ensure_ascii=True, separators=(",", ":")),
                900,
            ),
        )
        return fallback_outline


def call_openai_fast_qa(
    question: str,
    snippets: list[dict[str, Any]],
    chat_history: list[list[str]],
    refs: list[dict[str, Any]],
    citation_mode: str | None,
    primary_source_note: str = "",
    requested_language: str | None = None,
    allow_general_knowledge: bool = False,
) -> str | None:
    api_key, base_url, model, config_source = _resolve_fast_qa_llm_config()
    logger.warning(
        "fast_qa_llm_config source=%s model=%s base=%s key_present=%s",
        config_source,
        model,
        base_url,
        bool(api_key),
    )
    if is_placeholder_api_key(api_key):
        logger.warning(
            "fast_qa_disabled reason=missing_openai_key source=%s question=%s",
            config_source,
            _truncate_for_log(question, 220),
        )
        return None

    context_blocks = []
    for snippet in snippets[:API_FAST_QA_MAX_SNIPPETS]:
        source_name = str(snippet.get("source_name", "Indexed file"))
        page_label = str(snippet.get("page_label", "") or "").strip()
        text = str(snippet.get("text", "") or "").strip()
        doc_type = str(snippet.get("doc_type", "") or "").strip()
        ref_id = int(snippet.get("ref_id", 0) or 0)
        is_primary = bool(snippet.get("is_primary_source"))
        header_parts = [f"Ref: [{ref_id}] Source: {source_name}"]
        if page_label:
            header_parts.append(f"Page: {page_label}")
        if doc_type:
            header_parts.append(f"Type: {doc_type}")
        if is_primary:
            header_parts.append("Priority: primary")
        context_blocks.append(f"{' | '.join(header_parts)}\nExcerpt: {text}")

    visual_evidence: list[tuple[str, str, str, int]] = []
    seen_images: set[str] = set()
    for snippet in snippets:
        source_name = str(snippet.get("source_name", "Indexed file"))
        page_label = str(snippet.get("page_label", "") or "")
        ref_id = int(snippet.get("ref_id", 0) or 0)
        image_origin = snippet.get("image_origin")
        if not isinstance(image_origin, str) or not image_origin.startswith("data:image/"):
            continue
        if image_origin in seen_images:
            continue
        seen_images.add(image_origin)
        visual_evidence.append((source_name, page_label, image_origin, ref_id))
        if len(visual_evidence) >= max(0, API_FAST_QA_MAX_IMAGES):
            break
    history_blocks = []
    for turn in chat_history[-3:]:
        if not isinstance(turn, list) or len(turn) < 2:
            continue
        history_blocks.append(f"User: {turn[0]}\nAssistant: {turn[1]}")

    history_text = "\n\n".join(history_blocks) if history_blocks else "(none)"
    context_text = "\n\n".join(context_blocks)
    refs_text = "\n".join([f"[{ref['id']}] {ref['label']}" for ref in refs[: min(len(refs), 20)]])
    general_knowledge_mode = bool(allow_general_knowledge and not context_blocks)
    mode = resolve_required_citation_mode(citation_mode)
    if general_knowledge_mode:
        citation_instruction = (
            "No indexed source refs are available for this turn. "
            "Do not fabricate citations or source links."
        )
    elif mode == "footnote":
        citation_instruction = (
            "Keep the main paragraphs citation-free, then add a final 'Sources' section "
            "with refs in square brackets (for example [1], [2]) tied to the key claims."
        )
    else:
        citation_instruction = (
            "Cite factual claims with source refs in square brackets like [1], [2]. "
            "Every major claim should have at least one citation. "
            "Use the most specific ref excerpt that directly supports each cited claim. "
            "Number refs sequentially starting at [1] and reuse the same ref number when citing the same evidence."
        )
    temperature = max(0.0, min(1.0, float(API_FAST_QA_TEMPERATURE)))
    outline = _plan_adaptive_outline(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        question=question,
        history_text=history_text,
        refs_text=refs_text,
        context_text=context_text,
    )
    output_instruction = (
        "Output format rules:\n"
        "- Follow the provided response blueprint while adapting when evidence is missing.\n"
        "- Keep the answer directly relevant to the user's question.\n"
        "- Start with a direct answer in the first sentence.\n"
        "- Render blueprint sections as markdown headings only when there are multiple meaningful sections.\n"
        "- For direct questions, give a direct answer first, then provide evidence-backed supporting detail.\n"
        "- For broad or research-oriented questions, provide richer multi-section depth.\n"
        "- Choose structure per query (narrative paragraphs, headed sections, bullets, or tables); do not reuse a single fixed layout across responses.\n"
        "- Use natural prose by default; use headings, bullets, or tables only when they improve clarity.\n"
        "- Do not lead with isolated quoted fragments or decorative callouts unless the user explicitly asks for direct quotes.\n"
        "- Prefer complete sentences and coherent paragraphs over stylized snippets.\n"
        "- Keep section titles specific to the request domain; avoid generic reusable labels and reusable report skeletons.\n"
        "- Avoid promotional tone, filler, and repetitive phrasing.\n"
        "- Avoid unsupported inference; do not use 'typically', 'may', or similar hedging unless evidence explicitly indicates uncertainty.\n"
        "- For entity/detail lookup questions, provide exact fields from evidence instead of generic summaries.\n"
        "- When adding website links, avoid placeholder anchor text like 'here'; use meaningful link text.\n"
        "- If intent is unclear, ask one focused clarifying question and avoid speculative summaries.\n"
        "- Distinguish confirmed facts from inference when confidence is limited.\n"
        + (
            "- If indexed evidence is unavailable, answer from general knowledge and explicitly mark uncertainty when needed.\n"
            if general_knowledge_mode
            else "- If information is missing, say: Not visible in indexed content.\n"
        )
        + f"- {build_response_language_rule(requested_language=requested_language, latest_message=question)}\n"
        "- Use clean markdown and avoid malformed formatting."
    )
    if general_knowledge_mode:
        prompt = (
            "No indexed evidence matched this request. "
            "Answer the user question directly from reliable general knowledge. "
            "Be factual, concise, and explicit about uncertainty where relevant. "
            "Do not invent citations, documents, or source URLs. "
            f"{citation_instruction}\n\n"
            f"Response blueprint (generated by Maia planner):\n{json.dumps(outline, ensure_ascii=True)}\n\n"
            f"{output_instruction}\n\n"
            f"Recent chat history:\n{history_text}\n\n"
            f"Question: {question}"
        )
    else:
        prompt = (
            "Use the provided indexed context to answer the user question. "
            "When multiple sources are relevant, synthesize across them and call out agreements or differences. "
            "When a question asks what a PDF/image is about, adapt the structure to the document type and available evidence instead of a fixed template. "
            "If visual evidence is provided, use it to improve detail while clearly signaling assumptions. "
            "If a primary source target is present, prioritize that source in the answer and keep other sources secondary. "
            f"{citation_instruction}\n\n"
            f"Primary source guidance:\n{primary_source_note or '(none)'}\n\n"
            f"Response blueprint (generated by Maia planner):\n{json.dumps(outline, ensure_ascii=True)}\n\n"
            f"{output_instruction}\n\n"
            f"Source index:\n{refs_text or '(none)'}\n\n"
            f"Recent chat history:\n{history_text}\n\n"
            f"Indexed context:\n{context_text}\n\n"
            f"Question: {question}"
        )
    user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for source_name, page_label, image_origin, ref_id in visual_evidence:
        label = f"Visual evidence [{ref_id}] from {source_name}"
        if page_label:
            label += f" (page {page_label})"
        user_content.append({"type": "text", "text": label})
        user_content.append({"type": "image_url", "image_url": {"url": image_origin}})

    try:
        request_payload = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        (
                            "You are Maia. Use indexed evidence when available; when it is unavailable, answer from reliable general knowledge. "
                            "Never invent citations or pretend to have source evidence when none is provided. "
                            "Adapt structure to the user's question and available context; do not force fixed section templates. "
                            "Use concise sections and bullet points only when useful. "
                            "Keep output professional and specific. "
                        )
                        if general_knowledge_mode
                        else (
                            "You are Maia. Provide faithful answers from indexed evidence. "
                            "Adapt structure to the user's question and evidence; do not force fixed section templates. "
                            "Use concise sections and bullet points only when useful. "
                            "Keep output professional and specific. "
                        )
                        + f"{build_response_language_rule(requested_language=requested_language, latest_message=question)} "
                        + (
                            "Do not invent facts; acknowledge uncertainty when needed."
                            if general_knowledge_mode
                            else "Do not infer details that are not explicitly supported by evidence."
                        )
                    ),
                },
                {"role": "user", "content": user_content},
            ],
        }
        answer = str(
            _call_openai_chat_text(
                api_key=api_key,
                base_url=base_url,
                request_payload=request_payload,
                timeout_seconds=20,
            )
            or ""
        ).strip()
        if not answer:
            logger.warning(
                "fast_qa_empty_answer model=%s question=%s",
                model,
                _truncate_for_log(question, 220),
            )
        return answer or None
    except HTTPError as exc:
        logger.warning(
            "fast_qa_http_error model=%s question=%s error=%s",
            model,
            _truncate_for_log(question, 220),
            _truncate_for_log(exc, 280),
        )
        return None
    except Exception:
        logger.exception(
            "fast_qa_call_failed model=%s question=%s",
            model,
            _truncate_for_log(question, 220),
        )
        return None


def run_fast_chat_turn(
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
) -> dict[str, Any] | None:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")
    if request.command not in (None, "", DEFAULT_SETTING):
        logger.warning(
            "fast_qa_skipped reason=command_override command=%s",
            str(request.command or "").strip()[:80],
        )
        return None

    conversation_id, conversation_name, data_source, conversation_icon_key = get_or_create_conversation(
        user_id=user_id,
        conversation_id=request.conversation_id,
    )
    conversation_name, conversation_icon_key = maybe_autoname_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        current_name=conversation_name,
        message=message,
        agent_mode=request.agent_mode,
    )
    data_source = deepcopy(data_source or {})
    data_source["conversation_icon_key"] = conversation_icon_key
    chat_history = deepcopy(data_source.get("messages", []))
    chat_state = deepcopy(data_source.get("state", STATE))
    requested_language = resolve_response_language(request.language, message)

    selected_payload = build_selected_payload(
        context=context,
        user_id=user_id,
        existing_selected=data_source.get("selected", {}),
        requested_selected=request.index_selection,
    )
    url_targets = _resolve_contextual_url_targets(
        question=message,
        chat_history=chat_history,
        max_urls=6,
    )
    retrieval_query, is_follow_up, rewrite_reason = _rewrite_followup_question_for_retrieval(
        question=message,
        chat_history=chat_history,
        target_urls=url_targets,
    )
    retrieval_query = retrieval_query or message
    logger.warning(
        "fast_qa_retrieval_query follow_up=%s rewrite_reason=%s query=%s targets=%s question=%s",
        bool(is_follow_up),
        _truncate_for_log(rewrite_reason, 120),
        _truncate_for_log(retrieval_query, 220),
        ",".join(url_targets[:3]) if url_targets else "(none)",
        _truncate_for_log(message, 220),
    )

    retrieval_max_sources = max(API_FAST_QA_SOURCE_SCAN, API_FAST_QA_MAX_SOURCES)
    retrieval_max_chunks = max(18, int(API_FAST_QA_MAX_SNIPPETS) * 3)
    max_keep = max(1, int(API_FAST_QA_MAX_SNIPPETS))

    raw_snippets = load_recent_chunks_for_fast_qa(
        context=context,
        user_id=user_id,
        selected_payload=selected_payload,
        query=retrieval_query,
        max_sources=retrieval_max_sources,
        max_chunks=retrieval_max_chunks,
    )
    snippets, primary_source_note, selection_reason = _finalize_retrieved_snippets(
        question=message,
        chat_history=chat_history,
        retrieved_snippets=raw_snippets,
        selected_payload=selected_payload,
        target_urls=url_targets,
        mindmap_focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
        max_keep=max_keep,
    )

    if selection_reason == "no_snippets" and retrieval_query != message:
        logger.warning(
            "fast_qa_retrieval_retry fallback=literal_query first_query=%s question=%s",
            _truncate_for_log(retrieval_query, 220),
            _truncate_for_log(message, 220),
        )
        raw_snippets = load_recent_chunks_for_fast_qa(
            context=context,
            user_id=user_id,
            selected_payload=selected_payload,
            query=message,
            max_sources=retrieval_max_sources,
            max_chunks=retrieval_max_chunks,
        )
        snippets, primary_source_note, selection_reason = _finalize_retrieved_snippets(
            question=message,
            chat_history=chat_history,
            retrieved_snippets=raw_snippets,
            selected_payload=selected_payload,
            target_urls=url_targets,
            mindmap_focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
            max_keep=max_keep,
        )

    if selection_reason == "no_snippets":
        logger.warning(
            "fast_qa_skipped reason=no_snippets query=%s question=%s",
            _truncate_for_log(retrieval_query, 220),
            _truncate_for_log(message, 220),
        )
        if url_targets:
            logger.warning(
                "fast_qa_skipped reason=no_snippets_for_url_context targets=%s question=%s",
                ",".join(url_targets[:3]),
                _truncate_for_log(message, 220),
            )
        return None
    if selection_reason == "no_primary_for_url":
        logger.warning(
            "fast_qa_skipped reason=no_primary_for_url targets=%s question=%s",
            ",".join(url_targets[:3]),
            _truncate_for_log(message, 220),
        )
        return None
    if selection_reason == "no_primary_after_selection":
        logger.warning(
            "fast_qa_skipped reason=no_primary_after_selection targets=%s question=%s",
            ",".join(url_targets[:3]),
            _truncate_for_log(message, 220),
        )
        return None
    if selection_reason == "no_relevant_snippets_for_url":
        logger.warning(
            "fast_qa_skipped reason=no_relevant_snippets_for_url targets=%s question=%s",
            ",".join(url_targets[:3]),
            _truncate_for_log(message, 220),
        )
        return None

    evidence_sufficient, evidence_confidence, evidence_reason = _assess_evidence_sufficiency_with_llm(
        question=message,
        chat_history=chat_history,
        snippets=snippets,
        primary_source_note=primary_source_note,
        require_primary_source=bool(url_targets),
    )
    should_retry_retrieval = (
        not evidence_sufficient
        and bool(message)
        and (
            bool(url_targets)
            or bool(is_follow_up)
            or bool(chat_history)
        )
    )
    if should_retry_retrieval:
        expanded_query, expansion_reason = _expand_retrieval_query_for_gap(
            question=message,
            current_query=retrieval_query,
            chat_history=chat_history,
            snippets=snippets,
            insufficiency_reason=evidence_reason,
            target_urls=url_targets,
        )
        expanded_query = expanded_query or retrieval_query
        logger.warning(
            "fast_qa_retrieval_second_pass reason=%s insufficiency=%s query=%s question=%s",
            _truncate_for_log(expansion_reason, 140),
            _truncate_for_log(evidence_reason, 180),
            _truncate_for_log(expanded_query, 220),
            _truncate_for_log(message, 220),
        )
        if expanded_query != retrieval_query or selection_reason in {"no_relevant_snippets", ""}:
            second_raw_snippets = load_recent_chunks_for_fast_qa(
                context=context,
                user_id=user_id,
                selected_payload=selected_payload,
                query=expanded_query,
                max_sources=max(retrieval_max_sources, API_FAST_QA_MAX_SOURCES + 16),
                max_chunks=max(retrieval_max_chunks, int(API_FAST_QA_MAX_SNIPPETS) * 5),
            )
            second_snippets, second_primary_note, second_selection_reason = _finalize_retrieved_snippets(
                question=message,
                chat_history=chat_history,
                retrieved_snippets=second_raw_snippets,
                selected_payload=selected_payload,
                target_urls=url_targets,
                mindmap_focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
                max_keep=max_keep,
            )
            if second_selection_reason in {
                "no_primary_for_url",
                "no_primary_after_selection",
                "no_relevant_snippets_for_url",
            }:
                logger.warning(
                    "fast_qa_retrieval_second_pass_skipped reason=%s targets=%s question=%s",
                    second_selection_reason,
                    ",".join(url_targets[:3]),
                    _truncate_for_log(message, 220),
                )
            elif second_selection_reason != "no_snippets":
                second_sufficient, second_confidence, second_reason = _assess_evidence_sufficiency_with_llm(
                    question=message,
                    chat_history=chat_history,
                    snippets=second_snippets,
                    primary_source_note=second_primary_note,
                    require_primary_source=bool(url_targets),
                )
                if second_snippets and (
                    second_sufficient
                    or second_confidence > evidence_confidence
                    or not snippets
                ):
                    snippets = second_snippets
                    primary_source_note = second_primary_note
                    evidence_sufficient = second_sufficient
                    evidence_confidence = second_confidence
                    evidence_reason = second_reason
                    retrieval_query = expanded_query
                    logger.warning(
                        "fast_qa_retrieval_second_pass_applied sufficient=%s confidence=%.3f note=%s",
                        bool(evidence_sufficient),
                        float(evidence_confidence),
                        _truncate_for_log(evidence_reason, 180),
                    )
    if bool(url_targets) and not evidence_sufficient:
        logger.warning(
            "fast_qa_skipped reason=insufficient_evidence_for_url targets=%s confidence=%.3f note=%s question=%s",
            ",".join(url_targets[:3]),
            float(evidence_confidence),
            _truncate_for_log(evidence_reason, 180),
            _truncate_for_log(message, 220),
        )
        return None

    if snippets:
        snippets_with_refs, refs = assign_fast_source_refs(snippets)
        answer = call_openai_fast_qa(
            question=message,
            snippets=snippets_with_refs,
            chat_history=chat_history,
            refs=refs,
            citation_mode=request.citation,
            primary_source_note=primary_source_note,
            requested_language=requested_language,
        )
        if not answer:
            logger.warning(
                "fast_qa_skipped reason=no_model_answer snippets=%d refs=%d question=%s",
                len(snippets_with_refs),
                len(refs),
                _truncate_for_log(message, 220),
            )
            return None
        answer = normalize_fast_answer(answer)
        used_general_fallback = False
    else:
        logger.warning(
            "fast_qa_no_relevant_snippets question=%s",
            _truncate_for_log(message, 220),
        )
        snippets_with_refs, refs = [], []
        answer = call_openai_fast_qa(
            question=message,
            snippets=[],
            chat_history=chat_history,
            refs=[],
            citation_mode=request.citation,
            primary_source_note=primary_source_note,
            requested_language=requested_language,
            allow_general_knowledge=True,
        )
        used_general_fallback = bool(answer)
        if answer:
            answer = normalize_fast_answer(answer)
        else:
            answer = _build_no_relevant_evidence_answer(
                message,
                response_language=requested_language,
            )
            used_general_fallback = False

    resolved_citation_mode = resolve_required_citation_mode(request.citation)
    if refs:
        answer = render_fast_citation_links(
            answer=answer,
            refs=refs,
            citation_mode=resolved_citation_mode,
        )
    info_text = build_fast_info_html(snippets_with_refs, max_blocks=6)
    if refs or not used_general_fallback:
        answer = enforce_required_citations(
            answer=answer,
            info_html=info_text,
            citation_mode=resolved_citation_mode,
        )
    logger.warning(
        "fast_qa_completed snippets=%d refs=%d answer_chars=%d",
        len(snippets_with_refs),
        len(refs),
        len(answer),
    )
    source_usage = build_source_usage(
        snippets_with_refs=snippets_with_refs,
        refs=refs,
        answer_text=answer,
        enabled=MAIA_SOURCE_USAGE_HEATMAP_ENABLED,
    )
    claim_signal_summary = build_claim_signal_summary(
        answer_text=answer,
        refs=refs,
    )
    citation_quality_metrics = build_citation_quality_metrics(
        snippets_with_refs=snippets_with_refs,
        refs=refs,
        answer_text=answer,
    )
    max_citation_share = max(
        (float(item.get("citation_share", 0.0) or 0.0) for item in source_usage),
        default=0.0,
    )
    source_dominance_detected = bool(
        source_usage and max_citation_share > float(MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD)
    )
    source_dominance_warning = (
        "This answer depends heavily on one source; consider reviewing other documents for broader context."
        if source_dominance_detected
        else ""
    )
    info_panel = build_info_panel_copy(
        request_message=message,
        answer_text=answer,
        info_html=info_text,
        mode="ask",
        next_steps=[],
        web_summary={},
    )
    mindmap_payload: dict[str, Any] = {}
    if bool(request.use_mindmap):
        map_settings = dict(request.mindmap_settings or {})
        try:
            map_depth = int(map_settings.get("max_depth", 4))
        except Exception:
            map_depth = 4
        map_type = str(map_settings.get("map_type", "structure") or "structure").strip().lower()
        if map_type not in {"structure", "evidence", "work_graph"}:
            map_type = "structure"
        mindmap_payload = build_knowledge_map(
            question=message,
            context="\n\n".join(str(row.get("text", "") or "") for row in snippets[:8]),
            documents=snippets,
            answer_text=answer,
            max_depth=max(2, min(8, map_depth)),
            include_reasoning_map=bool(map_settings.get("include_reasoning_map", True)),
            source_type_hint=str(map_settings.get("source_type_hint", "") or ""),
            focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
            map_type=map_type,
        )
        info_panel["mindmap"] = mindmap_payload
    if source_usage:
        info_panel["source_usage"] = source_usage
    if claim_signal_summary:
        info_panel["claim_signal_summary"] = claim_signal_summary
    if citation_quality_metrics:
        info_panel["citation_quality_metrics"] = citation_quality_metrics
    if source_dominance_warning:
        info_panel["source_dominance_warning"] = source_dominance_warning
    if primary_source_note:
        info_panel["primary_source_note"] = primary_source_note
    if used_general_fallback:
        info_panel["answer_origin"] = "llm_general_knowledge"
    info_panel["citation_strength_ordering"] = bool(MAIA_CITATION_STRENGTH_ORDERING_ENABLED)
    info_panel["citation_strength_legend"] = (
        "Citation numbers are normalized per answer: each source appears once and numbering starts at 1."
    )

    messages = chat_history + [[message, answer]]
    retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
    retrieval_history.append(info_text)
    plot_history = deepcopy(data_source.get("plot_history", []))
    plot_history.append(None)
    message_meta = deepcopy(data_source.get("message_meta", []))
    turn_attachments = _normalize_request_attachments(request)
    message_meta.append(
        {
            "mode": "ask",
            "activity_run_id": None,
            "actions_taken": [],
            "sources_used": [],
            "source_usage": source_usage,
            "attachments": turn_attachments,
            "claim_signal_summary": claim_signal_summary,
            "citation_quality_metrics": citation_quality_metrics,
            "next_recommended_steps": [],
            "info_panel": info_panel,
            "mindmap": mindmap_payload,
        }
    )

    conversation_payload = {
        "selected": selected_payload,
        "messages": messages,
        "retrieval_messages": retrieval_history,
        "plot_history": plot_history,
        "message_meta": message_meta,
        "state": chat_state,
        "likes": deepcopy(data_source.get("likes", [])),
    }
    persist_conversation(conversation_id, conversation_payload)

    return {
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "message": message,
        "answer": answer,
        "info": info_text,
        "plot": None,
        "state": chat_state,
        "mode": "ask",
        "actions_taken": [],
        "sources_used": [],
        "source_usage": source_usage,
        "claim_signal_summary": claim_signal_summary,
        "citation_quality_metrics": citation_quality_metrics,
        "next_recommended_steps": [],
        "activity_run_id": None,
        "info_panel": info_panel,
        "mindmap": mindmap_payload,
    }
