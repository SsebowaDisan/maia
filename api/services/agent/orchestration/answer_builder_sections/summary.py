from __future__ import annotations

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
    lines.append("")
    lines.append("## Key Findings")
    browser_findings = ctx.runtime_settings.get("__latest_browser_findings")
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
        if title:
            lines.append(f"- Website analyzed: {title}")
        if url:
            lines.append(f"- Source URL: {url}")
        if browser_keywords:
            lines.append(f"- Observed keywords: {', '.join(browser_keywords[:10])}")
        if excerpt:
            lines.append(f"- Evidence note: {excerpt}")
    else:
        lines.append("- Findings are based on executed tools and indexed evidence.")

    if ctx.sources:
        unique_urls: list[str] = []
        for source in ctx.sources:
            url = str(source.url or "").strip()
            if not url or url in unique_urls:
                continue
            unique_urls.append(url)
        lines.append(f"- Sources used: {len(ctx.sources)}")
        if unique_urls:
            lines.append(f"- Primary source: {unique_urls[0]}")


def append_execution_issues(lines: list[str], ctx: AnswerBuildContext) -> None:
    failed_actions = [item for item in ctx.actions if item.status == "failed"]
    if not failed_actions:
        return
    lines.append("")
    lines.append("## Execution Issues")
    for item in failed_actions[:6]:
        lines.append(f"- {item.tool_id}: {compact(item.summary, 180)}")
