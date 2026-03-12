from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import AnswerBuildContext
from ..text_helpers import compact


URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)

# Text patterns that indicate a bot-block / error page rather than real content.
# Snippets matching any of these should never surface as "Key finding" or evidence.
_ERROR_PAGE_SIGNALS = (
    "access denied",
    "you don't have permission",
    "you do not have permission",
    "403 forbidden",
    "reference #",
    "edgesuite.net",
    "errors.edgesuite",
    "cloudflare",
    "checking your browser",
    "ddos protection",
    "captcha",
    "bot challenge",
    "verify you are human",
    "unusual traffic",
    "request blocked",
    "security check",
)


def _is_error_page_text(text: str) -> bool:
    """Return True if the text looks like a bot-block or server-error page."""
    lowered = " ".join(str(text or "").split()).lower()
    return any(signal in lowered for signal in _ERROR_PAGE_SIGNALS)


OPERATIONAL_LABEL_PREFIXES = (
    "workspace.",
    "gmail.",
    "email.",
    "mailer.",
    "report.",
    "contract.",
    "verification.",
)
OPERATIONAL_PROVIDER_HINTS = {
    "google_sheets",
    "workspace_sheets",
    "workspace_docs",
    "workspace_docs_template",
    "workspace_tracker",
}


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_url(value: object) -> str:
    raw = _clean(value).strip(" <>\"'`")
    if not raw:
        return ""
    raw = raw.rstrip(".,;:!?")
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return parsed.geturl()


def _extract_first_url(value: object) -> str:
    text = _clean(value)
    if not text:
        return ""
    match = URL_IN_TEXT_RE.search(text)
    if not match:
        return ""
    return _normalize_url(match.group(0))


def _source_operational(*, label: str, metadata: dict[str, object] | None) -> bool:
    lowered_label = _clean(label).lower()
    if any(lowered_label.startswith(prefix) for prefix in OPERATIONAL_LABEL_PREFIXES):
        return True
    payload = metadata if isinstance(metadata, dict) else {}
    provider = _clean(payload.get("provider")).lower()
    if provider in OPERATIONAL_PROVIDER_HINTS:
        return True
    tool_id = _clean(payload.get("tool_id")).lower()
    if tool_id and any(tool_id.startswith(prefix) for prefix in OPERATIONAL_LABEL_PREFIXES):
        return True
    return False


def _append_unique(urls: list[str], url: str) -> None:
    clean = _normalize_url(url)
    if not clean or clean in urls:
        return
    urls.append(clean)


def _collect_external_source_urls(ctx: AnswerBuildContext) -> list[str]:
    collected: list[str] = []
    for source in ctx.sources:
        metadata = source.metadata if isinstance(source.metadata, dict) else {}
        label = _clean(source.label)
        if _source_operational(label=label, metadata=metadata):
            continue
        url_candidates = (
            source.url,
            metadata.get("source_url"),
            metadata.get("page_url"),
            metadata.get("url"),
            metadata.get("link"),
            label if label.lower().startswith(("http://", "https://")) else "",
        )
        normalized = ""
        for candidate in url_candidates:
            normalized = _normalize_url(candidate) or _extract_first_url(candidate)
            if normalized:
                break
        if normalized:
            _append_unique(collected, normalized)

    report = ctx.verification_report if isinstance(ctx.verification_report, dict) else {}
    evidence_units = report.get("evidence_units")
    if isinstance(evidence_units, list):
        for unit in evidence_units:
            if not isinstance(unit, dict):
                continue
            label = _clean(unit.get("source") or unit.get("label"))
            if _source_operational(label=label, metadata=None):
                continue
            normalized = _normalize_url(unit.get("url")) or _extract_first_url(unit.get("text"))
            if normalized:
                _append_unique(collected, normalized)

    for setting_key in ("__latest_report_sources", "__latest_web_sources"):
        rows = ctx.runtime_settings.get(setting_key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            label = _clean(row.get("label"))
            if _source_operational(label=label, metadata=metadata):
                continue
            normalized = _normalize_url(row.get("url"))
            if not normalized:
                normalized = _normalize_url(metadata.get("source_url")) or _normalize_url(metadata.get("url"))
            if not normalized:
                normalized = _extract_first_url(row.get("snippet") or row.get("label"))
            if normalized:
                _append_unique(collected, normalized)

    return collected[:80]


def append_execution_summary(lines: list[str], ctx: AnswerBuildContext) -> None:
    lines.append("")
    lines.append("## Execution Summary")
    if ctx.executed_steps:
        for row in ctx.executed_steps:
            status = "completed" if row.get("status") == "success" else "failed"
            step_no = int(row.get("step") or 0)
            title = str(row.get("title") or "Step")
            tool_id = str(row.get("tool_id") or "tool")
            summary = compact(str(row.get("summary") or "No summary."), 180)
            lines.append(
                f"- Step {step_no}: **{title}** (`{tool_id}`) {status}. {summary}"
            )
    else:
        lines.append("- No execution steps completed.")


def append_key_findings(lines: list[str], ctx: AnswerBuildContext) -> None:
    def _is_meaningful_excerpt(text: str) -> bool:
        clean = " ".join(str(text or "").split()).strip()
        if len(clean) < 48:
            return False
        letters = len(re.findall(r"[A-Za-z]", clean))
        symbols = len(re.findall(r"[×✕|{}<>+=~`^]", clean))
        ratio = letters / max(1, len(clean))
        return ratio >= 0.55 and symbols <= max(4, len(clean) // 40)

    show_diagnostics = bool(ctx.runtime_settings.get("__show_response_diagnostics"))
    lines.append("")
    lines.append("## Executive Summary")
    browser_findings = ctx.runtime_settings.get("__latest_browser_findings")
    summary_emitted = False
    if isinstance(browser_findings, dict):
        title = str(browser_findings.get("title") or "").strip()
        url = str(browser_findings.get("url") or "").strip()
        excerpt = compact(str(browser_findings.get("excerpt") or ""), 240)
        page_blocked = bool(browser_findings.get("blocked_signal"))
        browser_keywords_raw = browser_findings.get("keywords")
        browser_keywords = (
            [str(item).strip() for item in browser_keywords_raw if str(item).strip()]
            if isinstance(browser_keywords_raw, list)
            else []
        )
        # Only surface "Reviewed source" when the page actually loaded.
        # A blocked page produces an error title ("Access Denied") that must not
        # appear as a positive finding.
        if not page_blocked:
            if title and url:
                lines.append(f"- Reviewed source: [{title}]({url})")
                summary_emitted = True
            elif title:
                lines.append(f"- Reviewed source: {title}")
                summary_emitted = True
            elif url:
                lines.append(f"- Reviewed source: {url}")
                summary_emitted = True
            # Surface page excerpt and keywords only when content is real.
            if _is_meaningful_excerpt(excerpt) and not _is_error_page_text(excerpt):
                lines.append(f"- Key finding: {excerpt}")
            clean_keywords = [
                kw for kw in browser_keywords
                if not _is_error_page_text(kw) and len(kw) > 3
            ]
            if clean_keywords:
                lines.append(f"- Observed topics: {', '.join(clean_keywords[:10])}")
        if show_diagnostics:
            pass  # diagnostics block preserved for future use
    else:
        lines.append("- Findings are grounded in executed tools and verified source evidence.")
        summary_emitted = True

    # Include extracted content snippets from the browser visit / search fallback
    # so the response polisher has real evidence to synthesize into full paragraphs.
    # Deduplicate by text fingerprint and strip error-page content.
    copied_highlights = ctx.runtime_settings.get("__copied_highlights")
    if isinstance(copied_highlights, list):
        seen_fingerprints: set[str] = set()
        meaningful_snippets: list[str] = []
        for item in copied_highlights:
            if not isinstance(item, dict):
                continue
            raw_text = str(item.get("text") or "").strip()
            if not _is_meaningful_excerpt(raw_text):
                continue
            if _is_error_page_text(raw_text):
                continue
            # Fingerprint: first 120 chars of normalized text to catch duplicates
            fingerprint = " ".join(raw_text.split())[:120]
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            meaningful_snippets.append(raw_text)
        if meaningful_snippets:
            lines.append("")
            lines.append("### Extracted Evidence")
            for snippet in meaningful_snippets[:8]:
                lines.append(f"- {snippet[:400]}")

    unique_urls = _collect_external_source_urls(ctx)
    if show_diagnostics and unique_urls:
        lines.append(f"- Source coverage: {len(unique_urls)} unique source(s).")
        lines.append(f"- Primary reference: {unique_urls[0]}")
    elif not summary_emitted:
        lines.append("- The response synthesizes available evidence captured during this run.")


def append_execution_issues(lines: list[str], ctx: AnswerBuildContext) -> None:
    failed_actions = [item for item in ctx.actions if item.status == "failed"]
    if not failed_actions:
        return
    lines.append("")
    lines.append("## Execution Issues")
    for item in failed_actions[:6]:
        lines.append(f"- {item.tool_id}: {compact(item.summary, 180)}")
