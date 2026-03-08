from __future__ import annotations

import html
import ipaddress
import re
import threading
from time import monotonic
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from api.routers.web_preview_fetch_helpers import (
    build_reader_page as _build_reader_page_impl,
)
from api.routers.web_preview_fetch_helpers import fetch_html as _fetch_html_impl
from api.routers.web_preview_fetch_helpers import (
    is_skeleton_html as _is_skeleton_html_impl,
)
from api.routers.web_preview_fetch_helpers import (
    playwright_available as _playwright_available_impl,
)
from api.routers.web_preview_fetch_helpers import (
    try_playwright_fetch as _try_playwright_fetch_impl,
)
from api.routers.web_preview_render_helpers import (
    sanitize_and_inject_preview_html as _sanitize_and_inject_preview_html_impl,
)
from api.services.agent.llm_runtime import call_json_response, env_bool

router = APIRouter(prefix="/api/web", tags=["web"])

_PREVIEW_CACHE_TTL_SECONDS = 120.0
_PREVIEW_MAX_BYTES = 2_500_000
_PREVIEW_TIMEOUT_SECONDS = 14
_PREVIEW_CACHE_LOCK = threading.Lock()
_PREVIEW_HTML_CACHE: dict[str, tuple[float, str, str]] = {}
_SCOPE_CACHE_TTL_SECONDS = 300.0
_SCOPE_CACHE_LOCK = threading.Lock()
_HIGHLIGHT_SCOPE_CACHE: dict[str, tuple[float, str]] = {}
_ALLOWED_HIGHLIGHT_SCOPES = {"tight", "sentence", "context", "block"}
_DEFAULT_HIGHLIGHT_SCOPE = "sentence"
_ALLOWED_PREVIEW_VIEWPORTS = {"desktop", "mobile"}
_DEFAULT_PREVIEW_VIEWPORT = "desktop"
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


def _should_uncloak_tag(raw_tag: str) -> bool:
    tag = str(raw_tag or "")
    class_match = re.search(r"\bclass\s*=\s*(['\"])(.*?)\1", tag, flags=re.IGNORECASE)
    class_value = str(class_match.group(2) if class_match else "").strip().lower()
    if not class_value:
        return False

    hide_tokens = ("popup", "dropdown", "menu", "nav", "header", "fixed", "offcanvas")
    if any(token in class_value for token in hide_tokens):
        return False

    show_tokens = (
        "js-content",
        "js-domains",
        "js-domainsparent",
        "js-spaceheight",
        "hero",
        "banner",
    )
    if any(token in class_value for token in show_tokens):
        return True

    if "hidden lg:block" in class_value:
        return True

    return False


def _strip_cloak_attrs_from_tag(raw_tag: str) -> str:
    return re.sub(
        r"\s(?:x-cloak|v-cloak|data-cloak)(?:\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+))?",
        "",
        str(raw_tag or ""),
        flags=re.IGNORECASE,
    )


def _normalize_text_fragment(raw_value: Any, *, max_chars: int) -> str:
    text = " ".join(str(raw_value or "").split()).strip()
    if not text:
        return ""
    text = re.sub(r"\bURL\s*Source\s*:\s*https?://[^\s<>'\")\]]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsource_url\s*[:=]\s*https?://[^\s<>'\")\]]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMarkdown\s*Content\s*:\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPublished\s*Time\s*:\s*[^|]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"https?://[^\s<>'\")\]]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", text)
    text = re.sub(r"[*#=|_]{2,}", " ", text)
    text = " ".join(text.split()).strip()
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.strip()


def _highlight_candidates(*, highlight: str, claim: str) -> list[str]:
    candidates: list[str] = []
    for raw in (highlight, claim):
        normalized = _normalize_text_fragment(raw, max_chars=220)
        if len(normalized) >= 8:
            candidates.append(normalized)
    if not candidates:
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped[:3]


def _normalize_highlight_scope(raw_value: Any) -> str:
    value = " ".join(str(raw_value or "").split()).strip().lower()
    if value in _ALLOWED_HIGHLIGHT_SCOPES:
        return value
    return _DEFAULT_HIGHLIGHT_SCOPE


def _normalize_preview_viewport(raw_value: Any) -> str:
    value = " ".join(str(raw_value or "").split()).strip().lower()
    if value in _ALLOWED_PREVIEW_VIEWPORTS:
        return value
    return _DEFAULT_PREVIEW_VIEWPORT


def _normalize_scope_text(raw_value: Any, *, max_chars: int = 260) -> str:
    text = " ".join(str(raw_value or "").split()).strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.strip()


def _heuristic_highlight_scope(*, question: str, highlight: str, claim: str) -> str:
    question_text = _normalize_scope_text(question, max_chars=260).lower()
    highlight_text = _normalize_scope_text(highlight, max_chars=260).lower()
    claim_text = _normalize_scope_text(claim, max_chars=260).lower()
    merged = " ".join([question_text, highlight_text, claim_text]).strip()
    if not merged:
        return _DEFAULT_HIGHLIGHT_SCOPE

    if re.search(r"\b(exact|verbatim|quote|wording|literal|line)\b", question_text):
        return "tight"
    if re.search(r"\b(where|which sentence|which paragraph|show sentence)\b", question_text):
        return "sentence"
    if re.search(r"\b(compare|difference|analysis|deep|comprehensive|detailed|full)\b", question_text):
        return "context"
    if re.search(r"\b(summarize|summary|overview|about|doing|explain|describe|what is|tell me)\b", question_text):
        return "sentence"
    if len(claim_text) >= 160 or len(highlight_text) >= 160:
        return "context"
    if len(claim_text) <= 40 and len(highlight_text) <= 40:
        return "tight"
    return _DEFAULT_HIGHLIGHT_SCOPE


def _resolve_highlight_scope(*, question: str, highlight: str, claim: str) -> str:
    normalized_question = _normalize_scope_text(question, max_chars=320)
    normalized_highlight = _normalize_scope_text(highlight, max_chars=320)
    normalized_claim = _normalize_scope_text(claim, max_chars=320)
    cache_key = "||".join(
        [
            normalized_question.lower(),
            normalized_highlight.lower(),
            normalized_claim.lower(),
        ]
    )
    now = monotonic()
    with _SCOPE_CACHE_LOCK:
        cached = _HIGHLIGHT_SCOPE_CACHE.get(cache_key)
        if cached and now < float(cached[0]):
            return _normalize_highlight_scope(cached[1])

    heuristic_scope = _heuristic_highlight_scope(
        question=normalized_question,
        highlight=normalized_highlight,
        claim=normalized_claim,
    )

    if (
        env_bool("MAIA_WEB_PREVIEW_HIGHLIGHT_SCOPE_LLM_ENABLED", default=True)
        and len(normalized_question) >= 6
    ):
        prompt = (
            "Choose one highlight scope for website citation evidence.\n"
            "Valid scopes: tight, sentence, context, block.\n"
            "Return strict JSON only: {\"scope\":\"tight|sentence|context|block\"}.\n"
            "Guidance:\n"
            "- tight: exact phrase emphasis.\n"
            "- sentence: whole sentence around the claim.\n"
            "- context: sentence plus nearby context.\n"
            "- block: broader paragraph-level emphasis for high-level explanatory questions.\n\n"
            f"User question: {normalized_question or '(none)'}\n"
            f"Claim text: {normalized_claim or '(none)'}\n"
            f"Highlight text: {normalized_highlight or '(none)'}\n"
            f"Heuristic suggestion: {heuristic_scope}"
        )
        llm_response = call_json_response(
            system_prompt=(
                "You optimize citation visibility in a website evidence preview. "
                "Respond with strict JSON only."
            ),
            user_prompt=prompt,
            temperature=0.0,
            timeout_seconds=5,
            max_tokens=90,
        )
        llm_scope = _normalize_highlight_scope(
            (llm_response or {}).get("scope", "") if isinstance(llm_response, dict) else ""
        )
        if llm_scope in _ALLOWED_HIGHLIGHT_SCOPES:
            with _SCOPE_CACHE_LOCK:
                _HIGHLIGHT_SCOPE_CACHE[cache_key] = (now + _SCOPE_CACHE_TTL_SECONDS, llm_scope)
            return llm_scope

    with _SCOPE_CACHE_LOCK:
        _HIGHLIGHT_SCOPE_CACHE[cache_key] = (now + _SCOPE_CACHE_TTL_SECONDS, heuristic_scope)
    return heuristic_scope


def _normalize_target_url(raw_value: Any) -> str:
    value = " ".join(str(raw_value or "").split()).strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except Exception:
        return ""
    scheme = str(parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return ""
    netloc = str(parsed.netloc or "").strip().lower()
    if not netloc:
        return ""
    host = netloc.split("@", 1)[-1].split(":", 1)[0]
    if not host or host in {"localhost", "127.0.0.1", "::1"}:
        return ""
    try:
        parsed_ip = ipaddress.ip_address(host)
    except ValueError:
        parsed_ip = None
    if parsed_ip and (
        parsed_ip.is_private
        or parsed_ip.is_loopback
        or parsed_ip.is_link_local
        or parsed_ip.is_reserved
        or parsed_ip.is_multicast
    ):
        return ""
    path = str(parsed.path or "")
    segments = [segment.strip().lower() for segment in path.split("/") if segment.strip()]
    if len(segments) == 1 and segments[0].rstrip(":") in _ARTIFACT_URL_PATH_SEGMENTS:
        return ""
    normalized_path = path or "/"
    return parsed._replace(
        scheme=scheme,
        netloc=netloc,
        path=normalized_path,
        fragment="",
    ).geturl()


def _preview_error_html(*, title: str, detail: str, source_url: str = "") -> str:
    escaped_title = html.escape(title, quote=True)
    escaped_detail = html.escape(detail, quote=True)
    escaped_source = html.escape(source_url, quote=True)
    link_row = (
        "<p class='maia-preview-meta'>"
        f"Source: <a href='{escaped_source}' target='_blank' rel='noopener noreferrer'>{escaped_source}</a>"
        "</p>"
        if escaped_source
        else ""
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>Website preview</title>"
        "<style>"
        "body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;"
        "background:#f5f5f7;color:#1d1d1f;}"
        ".maia-preview-wrap{max-width:860px;margin:20px auto;padding:16px;}"
        ".maia-preview-card{background:#fff;border:1px solid #d2d2d7;border-radius:14px;padding:16px;}"
        "h1{font-size:16px;margin:0 0 8px;}"
        "p{font-size:13px;line-height:1.5;margin:6px 0;}"
        ".maia-preview-meta{margin-top:10px;word-break:break-word;}"
        "a{color:#0a60ff;text-decoration:none;}a:hover{text-decoration:underline;}"
        "</style></head><body><div class='maia-preview-wrap'><div class='maia-preview-card'>"
        f"<h1>{escaped_title}</h1><p>{escaped_detail}</p>{link_row}</div></div></body></html>"
    )


def _is_google_workspace_source(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return False
    host = str(parsed.netloc or "").lower().split("@", 1)[-1].split(":", 1)[0]
    if host not in {"docs.google.com", "drive.google.com"}:
        return False
    path = str(parsed.path or "").lower()
    return any(
        marker in path
        for marker in (
            "/document/",
            "/spreadsheets/",
            "/presentation/",
            "/file/d/",
        )
    )


def _preview_fetch_error_html(*, source_url: str, detail: str) -> str:
    safe_source_url = _normalize_target_url(source_url) or str(source_url or "").strip()
    detail_text = " ".join(str(detail or "").split()).strip()
    if _is_google_workspace_source(safe_source_url) and (
        "401" in detail_text
        or "403" in detail_text
        or "unauthorized" in detail_text.lower()
        or "forbidden" in detail_text.lower()
    ):
        return _preview_error_html(
            title="Preview requires Google sign-in",
            detail=(
                "This citation points to a private Google Docs/Sheets/Drive file. "
                "The embedded preview cannot render private Google Workspace pages. "
                "Use Open to view it in your signed-in browser."
            ),
            source_url=safe_source_url,
        )
    message = "Could not load this source in the embedded preview."
    if detail_text:
        message = f"{message} {detail_text[:220]}"
    return _preview_error_html(
        title="Preview unavailable",
        detail=message,
        source_url=safe_source_url,
    )


def _fetch_html(url: str) -> tuple[str, str]:
    return _fetch_html_impl(
        url,
        preview_cache_ttl_seconds=_PREVIEW_CACHE_TTL_SECONDS,
        preview_max_bytes=_PREVIEW_MAX_BYTES,
        preview_timeout_seconds=_PREVIEW_TIMEOUT_SECONDS,
        preview_cache_lock=_PREVIEW_CACHE_LOCK,
        preview_html_cache=_PREVIEW_HTML_CACHE,
        preview_error_html_builder=_preview_error_html,
    )


def _playwright_available() -> bool:
    return _playwright_available_impl()


def _try_playwright_fetch(url: str) -> tuple[str, str] | None:
    return _try_playwright_fetch_impl(url)


def _is_skeleton_html(html_text: str) -> bool:
    return _is_skeleton_html_impl(html_text)


def _build_reader_page(*, html_text: str, source_url: str) -> str:
    return _build_reader_page_impl(html_text=html_text, source_url=source_url)


def _sanitize_and_inject_preview_html(
    *,
    html_text: str,
    source_url: str,
    highlight_phrases: list[str],
    highlight_scope: str = _DEFAULT_HIGHLIGHT_SCOPE,
    preview_viewport: str = _DEFAULT_PREVIEW_VIEWPORT,
) -> str:
    return _sanitize_and_inject_preview_html_impl(
        html_text=html_text,
        source_url=source_url,
        highlight_phrases=highlight_phrases,
        highlight_scope=highlight_scope,
        preview_viewport=preview_viewport,
        normalize_target_url_fn=_normalize_target_url,
        should_uncloak_tag_fn=_should_uncloak_tag,
        strip_cloak_attrs_from_tag_fn=_strip_cloak_attrs_from_tag,
        normalize_highlight_scope_fn=_normalize_highlight_scope,
        normalize_preview_viewport_fn=_normalize_preview_viewport,
        default_highlight_scope=_DEFAULT_HIGHLIGHT_SCOPE,
        default_preview_viewport=_DEFAULT_PREVIEW_VIEWPORT,
    )


@router.get("/preview", response_class=HTMLResponse)
def website_preview(
    url: str = Query(..., description="Source website URL to render"),
    highlight: str | None = Query(default=None, description="Citation text to highlight"),
    claim: str | None = Query(default=None, description="Claim text fallback for highlighting"),
    question: str | None = Query(default=None, description="User question used to adapt highlight scope"),
    viewport: str | None = Query(default=None, description="Preview viewport mode: desktop or mobile"),
) -> HTMLResponse:
    normalized_url = _normalize_target_url(url)
    if not normalized_url:
        raise HTTPException(status_code=400, detail="Invalid or blocked website URL.")
    try:
        html_text, final_url = _fetch_html(normalized_url)
    except HTTPException as exc:
        return HTMLResponse(
            content=_preview_fetch_error_html(source_url=normalized_url, detail=str(exc.detail)),
            status_code=200,
        )
    except Exception as exc:
        return HTMLResponse(
            content=_preview_fetch_error_html(source_url=normalized_url, detail=str(exc)),
            status_code=200,
        )

    if _is_skeleton_html(html_text):
        pw = _try_playwright_fetch(normalized_url)
        if pw:
            html_text, final_url = pw
            now = monotonic()
            with _PREVIEW_CACHE_LOCK:
                _PREVIEW_HTML_CACHE[normalized_url] = (
                    now + _PREVIEW_CACHE_TTL_SECONDS,
                    html_text,
                    final_url,
                )
        if _is_skeleton_html(html_text):
            html_text = _build_reader_page(
                html_text=html_text,
                source_url=_normalize_target_url(final_url) or normalized_url,
            )

    highlight_text = str(highlight or "")
    claim_text = str(claim or "")
    question_text = str(question or "")
    phrases = _highlight_candidates(highlight=highlight_text, claim=claim_text)
    scope = _resolve_highlight_scope(
        question=question_text,
        highlight=highlight_text,
        claim=claim_text,
    )
    rendered = _sanitize_and_inject_preview_html(
        html_text=html_text,
        source_url=_normalize_target_url(final_url) or normalized_url,
        highlight_phrases=phrases,
        highlight_scope=scope,
        preview_viewport=_normalize_preview_viewport(viewport),
    )
    return HTMLResponse(content=rendered, status_code=200)
