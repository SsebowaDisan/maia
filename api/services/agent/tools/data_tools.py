from __future__ import annotations

import csv
import io
from statistics import mean
from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _first_sentence(text: str, max_len: int = 220) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        return ""
    for token in (". ", "! ", "? "):
        if token in clean:
            clean = clean.split(token, 1)[0] + token.strip()
            break
    if len(clean) <= max_len:
        return clean
    return f"{clean[: max_len - 1].rstrip()}..."


class DataAnalysisTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="data.dataset.analyze",
        action_class="read",
        risk_level="medium",
        required_permissions=["data.read"],
        execution_policy="auto_execute",
        description="Run bounded analysis over provided tabular payload.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        csv_text = str(params.get("csv_text") or "").strip()
        rows_payload = params.get("rows")
        headers: list[str] = []
        rows: list[dict[str, Any]] = []

        if isinstance(rows_payload, list) and rows_payload and isinstance(rows_payload[0], dict):
            rows = [dict(item) for item in rows_payload]
            headers = list(rows[0].keys())
        elif csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            headers = list(reader.fieldnames or [])
            rows = [dict(row) for row in reader]

        if not rows:
            return ToolExecutionResult(
                summary="No dataset provided for analysis.",
                content="Provide `rows` or `csv_text` in request params to run data analysis.",
                data={},
                sources=[],
                next_steps=["Attach a CSV payload or selected file rows."],
                events=[
                    ToolTraceEvent(
                        event_type="tool_progress",
                        title="Dataset missing",
                        detail="No rows or CSV text available for analysis",
                    )
                ],
            )

        numeric_stats: dict[str, dict[str, float]] = {}
        for header in headers:
            values = [_as_float(row.get(header)) for row in rows]
            nums = [value for value in values if value is not None]
            if not nums:
                continue
            numeric_stats[header] = {
                "min": min(nums),
                "max": max(nums),
                "avg": mean(nums),
            }

        stats_lines = []
        for column, stats in numeric_stats.items():
            stats_lines.append(
                f"- {column}: min {stats['min']:.2f}, avg {stats['avg']:.2f}, max {stats['max']:.2f}"
            )

        content = (
            "### Dataset Analysis\n"
            f"- Rows: {len(rows)}\n"
            f"- Columns: {len(headers)}\n"
            f"- Numeric columns: {len(numeric_stats)}\n\n"
            "### Numeric Summary\n"
            + ("\n".join(stats_lines) if stats_lines else "- No numeric columns detected.")
        )
        return ToolExecutionResult(
            summary=f"Analyzed dataset with {len(rows)} rows.",
            content=content,
            data={"row_count": len(rows), "headers": headers, "stats": numeric_stats},
            sources=[],
            next_steps=[
                "Filter by key segment and rerun summary.",
                "Add trend windows if a date column exists.",
            ],
            events=[
                ToolTraceEvent(
                    event_type="doc_open",
                    title="Open dataset",
                    detail=f"Loaded {len(rows)} rows and {len(headers)} columns",
                    data={"row_count": len(rows), "column_count": len(headers)},
                ),
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Compute numeric summaries",
                    detail=f"Analyzed {len(numeric_stats)} numeric column(s)",
                    data={"numeric_columns": len(numeric_stats)},
                ),
            ],
        )


class ReportGenerationTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="report.generate",
        action_class="draft",
        risk_level="low",
        required_permissions=["report.write"],
        execution_policy="auto_execute",
        description="Generate structured executive report output.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        title = str(params.get("title") or "Executive Report").strip()
        summary = str(params.get("summary") or prompt).strip() or "No summary provided."
        summary = " ".join(summary.split())
        if len(summary) > 560:
            summary = f"{summary[:559].rstrip()}..."
        inferred_findings = context.settings.get("__latest_browser_findings")
        if isinstance(inferred_findings, dict):
            finding_title = str(inferred_findings.get("title") or "the website").strip()
            finding_url = str(inferred_findings.get("url") or "").strip()
            finding_excerpt = _first_sentence(str(inferred_findings.get("excerpt") or ""))
            finding_keywords = inferred_findings.get("keywords")
            keyword_line = (
                ", ".join(str(item).strip() for item in finding_keywords[:8])
                if isinstance(finding_keywords, list)
                else ""
            )
            summary = (
                f"{finding_title} appears to focus on industrial solutions and related services."
                + (f" Key terms observed: {keyword_line}." if keyword_line else "")
                + (f" Evidence URL: {finding_url}." if finding_url else "")
                + (f" Evidence note: {finding_excerpt}" if finding_excerpt else "")
            )
        highlights = params.get("highlights")
        if not isinstance(highlights, list):
            highlights = []

        actions = params.get("actions")
        if not isinstance(actions, list):
            actions = []

        highlight_lines = [f"- {str(item).strip()}" for item in highlights if str(item).strip()]
        action_lines = [f"- {str(item).strip()}" for item in actions if str(item).strip()]
        if not highlight_lines:
            highlight_lines = ["- Key findings will appear here once evidence is synthesized."]
        if not action_lines:
            action_lines = ["- Validate findings and assign an owner + timeline."]

        content = "\n".join(
            [
                f"## {title}",
                "",
                "### Executive Summary",
                summary,
                "",
                "### Highlights",
                *highlight_lines[:8],
                "",
                "### Action Plan",
                *action_lines[:8],
            ]
        )
        context.settings["__latest_report_title"] = title
        context.settings["__latest_report_content"] = content
        return ToolExecutionResult(
            summary=f"Generated report draft: {title}",
            content=content,
            data={"title": title},
            sources=[],
            next_steps=[
                "Attach owner/timeline for each action.",
                "Publish to Docs/Slack/Email channels.",
            ],
            events=[
                ToolTraceEvent(
                    event_type="doc_open",
                    title="Open report template",
                    detail=f"Preparing report draft: {title}",
                    data={"title": title},
                ),
                ToolTraceEvent(
                    event_type="doc_insert_text",
                    title="Populate report sections",
                    detail="Filled summary, highlights, and action plan sections",
                    data={"title": title},
                ),
            ],
        )
