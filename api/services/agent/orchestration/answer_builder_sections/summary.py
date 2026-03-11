from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import AnswerBuildContext
from ..text_helpers import compact


URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
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
        browser_keywords_raw = browser_findings.get("keywords")
        browser_keywords = (
            [str(item).strip() for item in browser_keywords_raw if str(item).strip()]
            if isinstance(browser_keywords_raw, list)
            else []
        )
        if title and url:
            lines.append(f"- Reviewed source: [{title}]({url})")
            summary_emitted = True
        elif title:
            lines.append(f"- Reviewed source: {title}")
            summary_emitted = True
        elif url:
            lines.append(f"- Reviewed source: {url}")
            summary_emitted = True
        if show_diagnostics and browser_keywords:
            lines.append(f"- Observed keywords: {', '.join(browser_keywords[:10])}")
        if show_diagnostics and _is_meaningful_excerpt(excerpt):
            lines.append(f"- Evidence note: {excerpt}")
    else:
        lines.append("- Findings are grounded in executed tools and verified source evidence.")
        summary_emitted = True

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
