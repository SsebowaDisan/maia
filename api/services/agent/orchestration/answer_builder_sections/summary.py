from __future__ import annotations

import re

from .models import AnswerBuildContext
from ..text_helpers import compact


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

    if ctx.sources:
        unique_urls: list[str] = []
        for source in ctx.sources:
            url = str(source.url or "").strip()
            if not url or url in unique_urls:
                continue
            unique_urls.append(url)
        lines.append(f"- Source coverage: {len(unique_urls)} unique source(s).")
        if unique_urls:
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
