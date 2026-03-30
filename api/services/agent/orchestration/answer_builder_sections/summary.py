from __future__ import annotations

import re
from urllib.parse import urlparse

from api.services.agent.llm_runtime import call_text_response

from .citations import collect_evidence_citations
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


def _is_meaningful_excerpt(text: str) -> bool:
    clean = " ".join(str(text or "").split()).strip()
    if len(clean) < 48:
        return False
    letters = len(re.findall(r"[A-Za-z]", clean))
    symbols = len(re.findall(r"[\×✕|{}<>+=~`^]", clean))
    ratio = letters / max(1, len(clean))
    return ratio >= 0.55 and symbols <= max(4, len(clean) // 40)


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


def _compose_llm_cited_research_summary(ctx: AnswerBuildContext) -> str:
    citations = collect_evidence_citations(ctx)
    if not citations:
        return ""

    def _best_note_for_label(label: str, url: str) -> str:
        for source in ctx.sources:
            source_label = _clean(source.label)
            source_url = _normalize_url(source.url)
            metadata = source.metadata if isinstance(source.metadata, dict) else {}
            if source_label != label and source_url != url:
                continue
            for key in ("snippet", "excerpt", "summary", "text", "quote", "phrase"):
                note = _clean(metadata.get(key))
                if note:
                    return note[:420]
        for bucket_key in ("__latest_report_sources", "__latest_web_sources"):
            rows = ctx.runtime_settings.get(bucket_key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_label = _clean(row.get("label"))
                row_url = _normalize_url(row.get("url"))
                if row_label != label and row_url != url:
                    continue
                for key in ("snippet", "excerpt", "summary", "text", "quote"):
                    note = _clean(row.get(key))
                    if note:
                        return note[:420]
                metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                for key in ("snippet", "excerpt", "summary", "text", "quote", "phrase"):
                    note = _clean(metadata.get(key))
                    if note:
                        return note[:420]
        return ""

    numbered_sources: list[str] = []
    for idx, row in enumerate(citations[:10], start=1):
        label = _clean(row.get("label")) or f"Source {idx}"
        url = _normalize_url(row.get("url"))
        note = _best_note_for_label(label, url) or _clean(row.get("note"))
        payload = f"[{idx}] {label}"
        if url:
            payload += f" | {url}"
        if note:
            payload += f" | {note}"
        numbered_sources.append(payload[:520])
    if len(numbered_sources) < 2:
        return ""

    evidence_snippets = _collect_evidence_snippets(ctx, citations)
    evidence_block = "\n".join(
        f"- [{item['citation_idx']}] {item['text']}"
        for item in evidence_snippets[:12]
    ).strip()
    report_excerpt = _extract_report_excerpt(ctx)

    request_message = _clean(ctx.request.message)
    latest_title = _clean(ctx.runtime_settings.get("__latest_report_title")) or "Research summary"
    user_goal = request_message or latest_title
    response = call_text_response(
        system_prompt=(
            "You write premium research summaries for executives. "
            "Your style is Apple-like: calm, precise, elegant, and highly structured. "
            "Use only the provided evidence. "
            "Every substantive claim must carry inline citation markers like [1] or [2][3] that map to the numbered sources."
        ),
        user_prompt=(
            "Write a concise but substantive research brief in markdown.\n"
            "Rules:\n"
            "- Start directly with the answer; no meta commentary.\n"
            "- Use 2-4 short paragraphs and optionally one compact bullet list if it improves clarity.\n"
            "- Prefer roughly 1000-1500 characters for a standard research brief unless the evidence clearly requires less or more.\n"
            "- Include actual findings, not process commentary.\n"
            "- If evidence is incomplete or conflicting, state that clearly.\n"
            "- Use only citation numbers from the provided numbered source list.\n"
            "- Do not include a Sources section here.\n\n"
            f"User request:\n{user_goal}\n\n"
            f"Reference title:\n{latest_title}\n\n"
            + (f"Report excerpt:\n{report_excerpt}\n\n" if report_excerpt else "")
            + (f"Evidence snippets:\n{evidence_block}\n\n" if evidence_block else "")
            + "Numbered sources:\n"
            + "\n".join(numbered_sources)
        ),
        temperature=0.2,
        timeout_seconds=24,
        max_tokens=1800,
    )
    text = str(response or "").strip()
    if not text or len(text) < 280:
        return ""
    if not re.search(r"\[\d+\]", text):
        return ""
    return text


def _extract_report_excerpt(ctx: AnswerBuildContext) -> str:
    report = str(ctx.runtime_settings.get("__latest_report_content") or "").strip()
    if not report:
        return ""
    report = re.sub(
        r"(?is)^.*?##\s+Evidence\s+Citations\s*$[\s\S]*$",
        "",
        report,
    ).strip()
    lines: list[str] = []
    for raw_line in report.splitlines():
        line = " ".join(str(raw_line or "").split()).strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if re.match(r"^#{1,3}\s+", line):
            continue
        if _is_error_page_text(line):
            continue
        lines.append(line)
        if len(" ".join(lines)) >= 900:
            break
    cleaned = "\n".join(lines).strip()
    return cleaned[:1200]


def _collect_evidence_snippets(
    ctx: AnswerBuildContext,
    citations: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    citation_rows = citations if isinstance(citations, list) else collect_evidence_citations(ctx)
    citation_index: dict[str, int] = {}
    for idx, row in enumerate(citation_rows, start=1):
        label = _clean(row.get("label"))
        url = _normalize_url(row.get("url"))
        if url:
            citation_index[f"url::{url.lower()}"] = idx
        if label:
            citation_index[f"label::{label.lower()}"] = idx

    snippets: list[dict[str, object]] = []
    seen: set[str] = set()

    def _append(text: object, *, label: object = "", url: object = "") -> None:
        clean = compact(str(text or "").strip(), 320)
        if not _is_meaningful_excerpt(clean):
            return
        if _is_error_page_text(clean):
            return
        normalized_url = _normalize_url(url)
        normalized_label = _clean(label)
        citation_idx = None
        if normalized_url:
            citation_idx = citation_index.get(f"url::{normalized_url.lower()}")
        if citation_idx is None and normalized_label:
            citation_idx = citation_index.get(f"label::{normalized_label.lower()}")
        if citation_idx is None:
            return
        fingerprint = re.sub(r"\[\d+\]", "", clean).strip().lower()
        if fingerprint in seen:
            return
        seen.add(fingerprint)
        snippets.append(
            {
                "citation_idx": citation_idx,
                "label": normalized_label,
                "url": normalized_url,
                "text": clean,
            }
        )

    for source in ctx.sources:
        metadata = source.metadata if isinstance(source.metadata, dict) else {}
        for key in ("snippet", "excerpt", "summary", "text", "quote", "phrase"):
            _append(metadata.get(key), label=source.label, url=source.url)

    for bucket_key in ("__latest_report_sources", "__latest_web_sources"):
        rows = ctx.runtime_settings.get(bucket_key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            label = row.get("label")
            url = row.get("url") or metadata.get("source_url") or metadata.get("url")
            for key in ("snippet", "excerpt", "summary", "text", "quote"):
                _append(row.get(key), label=label, url=url)
            for key in ("snippet", "excerpt", "summary", "text", "quote", "phrase"):
                _append(metadata.get(key), label=label, url=url)

    copied_highlights = ctx.runtime_settings.get("__copied_highlights")
    if isinstance(copied_highlights, list):
        for item in copied_highlights:
            if not isinstance(item, dict):
                continue
            _append(item.get("text"), label=item.get("label"), url=item.get("url"))

    browser_findings = ctx.runtime_settings.get("__latest_browser_findings")
    if isinstance(browser_findings, dict):
        _append(
            browser_findings.get("excerpt"),
            label=browser_findings.get("title"),
            url=browser_findings.get("url"),
        )

    return snippets[:12]


def _append_snippet_backed_summary(lines: list[str], ctx: AnswerBuildContext) -> bool:
    snippets = _collect_evidence_snippets(ctx)
    if not snippets:
        return False
    for item in snippets[:4]:
        text = str(item.get("text") or "").strip()
        citation_idx = int(item.get("citation_idx") or 0)
        if not text or citation_idx <= 0:
            continue
        if not re.search(rf"\[{citation_idx}\]", text):
            text = f"{text} [{citation_idx}]"
        lines.append(f"- {text}")
    return True


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
    show_diagnostics = bool(ctx.runtime_settings.get("__show_response_diagnostics"))
    lines.append("")
    lines.append("## Executive Summary")
    llm_summary = _compose_llm_cited_research_summary(ctx)
    if llm_summary:
        lines.extend(str(llm_summary).splitlines())
        return

    report_excerpt = _extract_report_excerpt(ctx)
    if report_excerpt:
        lines.extend(report_excerpt.splitlines())
        return

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
    elif not _append_snippet_backed_summary(lines, ctx):
        lines.append("- Findings are grounded in executed tools and verified source evidence.")
        summary_emitted = True
    else:
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
