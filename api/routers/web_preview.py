from __future__ import annotations

import html
import ipaddress
import json
import re
import threading
from time import monotonic
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

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

    # Keep navigation/overlay containers hidden to avoid showing opened mobile/mega menus.
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

    # Keep desktop media containers visible when scripts are stripped.
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
    now = monotonic()
    with _PREVIEW_CACHE_LOCK:
        cached = _PREVIEW_HTML_CACHE.get(url)
        if cached and now < float(cached[0]):
            return cached[1], cached[2]

    request = Request(
        url,
        method="GET",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36 MaiaPreview/1.0"
            ),
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
            "Connection": "close",
        },
    )
    try:
        with urlopen(request, timeout=_PREVIEW_TIMEOUT_SECONDS) as response:
            content_type = " ".join(str(response.headers.get("Content-Type", "")).split()).lower()
            if "html" not in content_type and "xhtml" not in content_type:
                return (
                    _preview_error_html(
                        title="Preview unavailable",
                        detail=(
                            "This source is not an HTML page. Use Open to view the original "
                            "resource in a new tab."
                        ),
                        source_url=str(response.geturl() or url),
                    ),
                    str(response.geturl() or url),
                )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > _PREVIEW_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Website preview payload is too large.",
                    )
                chunks.append(chunk)
            payload = b"".join(chunks)
            charset = str(response.headers.get_content_charset() or "").strip() or "utf-8"
            try:
                html_text = payload.decode(charset, errors="replace")
            except Exception:
                html_text = payload.decode("utf-8", errors="replace")
            final_url = str(response.geturl() or url)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Website fetch failed: {exc}") from exc

    with _PREVIEW_CACHE_LOCK:
        _PREVIEW_HTML_CACHE[url] = (now + _PREVIEW_CACHE_TTL_SECONDS, html_text, final_url)
        if len(_PREVIEW_HTML_CACHE) > 128:
            stale_keys = [
                key
                for key, (expiry, _html, _final_url) in _PREVIEW_HTML_CACHE.items()
                if now >= float(expiry)
            ]
            for key in stale_keys:
                _PREVIEW_HTML_CACHE.pop(key, None)
            overflow = len(_PREVIEW_HTML_CACHE) - 128
            if overflow > 0:
                for key in list(_PREVIEW_HTML_CACHE.keys())[:overflow]:
                    _PREVIEW_HTML_CACHE.pop(key, None)
    return html_text, final_url


def _sanitize_and_inject_preview_html(
    *,
    html_text: str,
    source_url: str,
    highlight_phrases: list[str],
    highlight_scope: str = _DEFAULT_HIGHLIGHT_SCOPE,
) -> str:
    text = str(html_text or "")
    lower = text.lower()
    if "<html" not in lower:
        text = f"<!doctype html><html><head></head><body>{text}</body></html>"
    if "<head" not in text.lower():
        text = re.sub(
            r"(<html\b[^>]*>)",
            r"\1<head></head>",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    if "<body" not in text.lower():
        if re.search(r"</head>", text, flags=re.IGNORECASE):
            text = re.sub(r"</head>", "</head><body>", text, count=1, flags=re.IGNORECASE)
            if re.search(r"</html>", text, flags=re.IGNORECASE):
                text = re.sub(r"</html>", "</body></html>", text, count=1, flags=re.IGNORECASE)
            else:
                text = f"{text}</body>"

    text = re.sub(
        r"<(script|iframe|object|embed)\b[^>]*>[\s\S]*?</\1\s*>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<(script|iframe|object|embed)\b[^>]*\/?>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<meta\b[^>]*http-equiv\s*=\s*['\"]?refresh['\"]?[^>]*>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\son[a-zA-Z0-9_-]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Selectively reveal framework-cloaked content that carries core page evidence,
    # while keeping navigation/menu overlays hidden.
    def _maybe_uncloak_tag(match: re.Match[str]) -> str:
        tag = str(match.group(0) or "")
        if not re.search(
            r"\s(?:x-cloak|v-cloak|data-cloak)(?:\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+))?",
            tag,
            flags=re.IGNORECASE,
        ):
            return tag
        if not _should_uncloak_tag(tag):
            return tag
        return _strip_cloak_attrs_from_tag(tag)

    text = re.sub(r"<[a-zA-Z][^>]*>", _maybe_uncloak_tag, text)

    def _rewrite_anchor_href(match: re.Match[str]) -> str:
        prefix = str(match.group(1) or "")
        raw_href = " ".join(str(match.group(2) or "").split()).strip()
        suffix = str(match.group(3) or "")
        if raw_href.startswith("#"):
            return f"{prefix}{html.escape(raw_href, quote=True)}{suffix}"
        absolute = _normalize_target_url(urljoin(source_url, html.unescape(raw_href)))
        preview_href = f"/api/web/preview?url={quote_plus(absolute)}" if absolute else "#"
        safe_href = html.escape(preview_href, quote=True)
        patched_suffix = re.sub(
            r"\starget\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
            "",
            suffix,
            flags=re.IGNORECASE,
        )
        patched_suffix = re.sub(
            r"\srel\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
            "",
            patched_suffix,
            flags=re.IGNORECASE,
        )
        patched_suffix = patched_suffix[:-1] + " target='_self' rel='noopener noreferrer'>"
        return f"{prefix}{safe_href}{patched_suffix}"

    text = re.sub(
        r"(<a\b[^>]*\bhref=['\"])([^'\"]+)(['\"][^>]*>)",
        _rewrite_anchor_href,
        text,
        flags=re.IGNORECASE,
    )
    scope = _normalize_highlight_scope(highlight_scope)

    style_block = (
        "<style>"
        ".opacity-0{opacity:1 !important;}"
        ".js-content{opacity:1 !important;}"
        "img.js-image,img[class*='js-image'],picture img{"
        "opacity:1 !important;"
        "visibility:visible !important;"
        "}"
        ".maia-citation-region{"
        "background:rgba(255,233,107,.2) !important;"
        "border-radius:.5em;"
        "box-shadow:inset 0 0 0 1px rgba(173,121,0,.22);"
        "padding:.16em .26em;"
        "}"
        "mark.maia-citation-highlight{"
        "background:#ffe96b !important;"
        "color:inherit !important;"
        "padding:.14em .24em;"
        "margin:0 .01em;"
        "border-radius:.24em;"
        "line-height:1.45;"
        "-webkit-box-decoration-break:clone;"
        "box-decoration-break:clone;"
        "box-shadow:0 0 0 1px rgba(173,121,0,.25);"
        "}"
        "body[data-maia-highlight-scope='tight'] mark.maia-citation-highlight{padding:.06em .14em;border-radius:.16em;line-height:1.25;}"
        "body[data-maia-highlight-scope='sentence'] mark.maia-citation-highlight{padding:.16em .30em;border-radius:.26em;line-height:1.55;}"
        "body[data-maia-highlight-scope='context'] mark.maia-citation-highlight,body[data-maia-highlight-scope='block'] mark.maia-citation-highlight{padding:.20em .40em;border-radius:.32em;line-height:1.65;}"
        ".maia-citation-region mark.maia-citation-highlight{background:#ffe14f !important;}"
        "mark.maia-citation-highlight.maia-citation-active{"
        "outline:2px solid rgba(173,121,0,.45);"
        "outline-offset:1px;"
        "}"
        "</style>"
    )
    script_block = (
        "<script>"
        "(function(){"
        "const phrases="
        + json.dumps(highlight_phrases, ensure_ascii=True)
        + ";"
        "const highlightScope="
        + json.dumps(scope, ensure_ascii=True)
        + ";"
        "const cleaned=[...new Set((phrases||[]).map((row)=>String(row||'').trim()).filter((row)=>row.length>=8))].slice(0,3);"
        "if(!cleaned.length||!document.body){return;}"
        "document.body.setAttribute('data-maia-highlight-scope',highlightScope);"
        "const skipTags=new Set(['SCRIPT','STYLE','NOSCRIPT','MARK','TEXTAREA','TITLE']);"
        "function nearestBoundary(raw,idx,direction){"
        "const marks=['.','!','?',String.fromCharCode(10)];"
        "if(direction<0){let found=-1;for(const mark of marks){const pos=raw.lastIndexOf(mark,idx);if(pos>found){found=pos;}}return found;}"
        "let found=raw.length;"
        "for(const mark of marks){const pos=raw.indexOf(mark,idx);if(pos>=0&&pos<found){found=pos;}}"
        "return found===raw.length?-1:found;"
        "}"
        "function expandedRange(raw,idx,queryLength){"
        "let start=idx;let end=idx+queryLength;"
        "if(highlightScope==='context'){start=Math.max(0,idx-90);end=Math.min(raw.length,idx+queryLength+90);}"
        "if(highlightScope==='sentence'||highlightScope==='block'){"
        "const left=nearestBoundary(raw,idx-1,-1);"
        "const right=nearestBoundary(raw,idx+queryLength,1);"
        "start=left>=0?left+1:0;"
        "end=right>=0?right+1:raw.length;"
        "}"
        "while(start<raw.length&&/\\s/.test(raw[start])){start+=1;}"
        "while(end>start&&/\\s/.test(raw[end-1])){end-=1;}"
        "if(end<=start){start=idx;end=idx+queryLength;}"
        "return [start,end];"
        "}"
        "function findAndMark(phrase,maxHits){"
        "const query=String(phrase||'');"
        "if(!query){return 0;}"
        "const qLower=query.toLowerCase();"
        "const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode(node){"
        "if(!node||!node.parentElement){return NodeFilter.FILTER_REJECT;}"
        "if(skipTags.has(node.parentElement.tagName)){return NodeFilter.FILTER_REJECT;}"
        "const value=String(node.nodeValue||'');"
        "if(!value||value.trim().length<qLower.length){return NodeFilter.FILTER_REJECT;}"
        "if(String(node.parentElement.className||'').includes('maia-citation-highlight')){return NodeFilter.FILTER_REJECT;}"
        "return value.toLowerCase().includes(qLower)?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT;"
        "}});"
        "const nodes=[];let current=null;"
        "while((current=walker.nextNode())){nodes.push(current);}"
        "let hits=0;"
        "for(const node of nodes){"
        "if(hits>=maxHits){break;}"
        "const raw=String(node.nodeValue||'');"
        "const idx=raw.toLowerCase().indexOf(qLower);"
        "if(idx<0){continue;}"
        "const range=expandedRange(raw,idx,query.length);"
        "const start=range[0];"
        "const end=range[1];"
        "const before=raw.slice(0,start);"
        "const match=raw.slice(start,end);"
        "const after=raw.slice(end);"
        "const frag=document.createDocumentFragment();"
        "if(before){frag.appendChild(document.createTextNode(before));}"
        "const mark=document.createElement('mark');"
        "mark.className='maia-citation-highlight';"
        "mark.textContent=match;"
        "frag.appendChild(mark);"
        "if(after){frag.appendChild(document.createTextNode(after));}"
        "if(node.parentNode){node.parentNode.replaceChild(frag,node);hits+=1;}"
        "}"
        "return hits;"
        "}"
        "let total=0;"
        "for(const phrase of cleaned){"
        "total+=findAndMark(phrase,total>0?1:3);"
        "if(total>=3){break;}"
        "}"
        "const first=document.querySelector('mark.maia-citation-highlight');"
        "if(first){first.classList.add('maia-citation-active');"
        "const region=(first.closest('p,li,blockquote,td,th,h1,h2,h3,h4,h5,h6,figcaption')||first.parentElement);"
        "if((highlightScope==='context'||highlightScope==='block')&&region&&region!==document.body&&region.classList){region.classList.add('maia-citation-region');}"
        "setTimeout(()=>{try{first.scrollIntoView({block:'center',inline:'nearest',behavior:'smooth'});}catch(_err){}},120);}"
        "})();"
        "</script>"
    )
    head_injection = f"<base href='{html.escape(source_url, quote=True)}'/>{style_block}"
    if re.search(r"</head>", text, flags=re.IGNORECASE):
        text = re.sub(
            r"</head>",
            lambda _match: f"{head_injection}</head>",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        text = f"<head>{head_injection}</head>{text}"
    if re.search(r"</body>", text, flags=re.IGNORECASE):
        text = re.sub(
            r"</body>",
            lambda _match: f"{script_block}</body>",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        text = f"{text}{script_block}"
    return text


@router.get("/preview", response_class=HTMLResponse)
def website_preview(
    url: str = Query(..., description="Source website URL to render"),
    highlight: str | None = Query(default=None, description="Citation text to highlight"),
    claim: str | None = Query(default=None, description="Claim text fallback for highlighting"),
    question: str | None = Query(default=None, description="User question used to adapt highlight scope"),
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
    )
    return HTMLResponse(content=rendered, status_code=200)
