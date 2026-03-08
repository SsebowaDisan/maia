from __future__ import annotations

import csv
import io
from statistics import mean
from typing import Any

from api.services.agent.llm_runtime import call_text_response
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.data_tools_helpers import (
    _analysis_paragraphs_with_llm,
    _analytics_section_lines,
    _as_float,
    _auto_highlights_from_sources,
    _classify_report_intent_with_llm,
    _draft_direct_answer,
    _event,
    _extract_location_signal_with_llm,
    _fallback_analysis_paragraphs,
    _first_sentence,
    _normalize_source_rows,
    _prefers_simple_explanation,
    _redact_delivery_targets,
    _reference_lines,
    _report_delivery_targets,
    _simple_explanation_lines,
)

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
        del context, prompt
        events: list[ToolTraceEvent] = []
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
                    _event(
                        tool_id=self.metadata.tool_id,
                        event_type="tool_failed",
                        title="Dataset missing",
                        detail="No rows or CSV text available for analysis",
                        data={"remediation": "Provide rows or csv_text and retry."},
                    )
                ],
            )
        row_count = len(rows)
        col_count = len(headers)
        events.append(
            _event(
                tool_id=self.metadata.tool_id,
                event_type="prepare_request",
                title="Prepare dataset",
                detail=f"Loaded {row_count} rows and {col_count} columns",
                data={"row_count": row_count, "column_count": col_count},
            )
        )
        events.append(
            _event(
                tool_id=self.metadata.tool_id,
                event_type="api_call_started",
                title="Compute numeric summaries",
                detail="Analyzing numeric ranges and averages",
            )
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
        events.append(
            _event(
                tool_id=self.metadata.tool_id,
                event_type="api_call_completed",
                title="Compute numeric summaries completed",
                detail=f"Analyzed {len(numeric_stats)} numeric column(s)",
                data={"numeric_columns": len(numeric_stats)},
            )
        )
        events.append(
            _event(
                tool_id=self.metadata.tool_id,
                event_type="normalize_response",
                title="Normalize analysis output",
                detail=f"rows={row_count}, columns={col_count}",
                data={"row_count": row_count, "column_count": col_count},
            )
        )

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
            summary=f"Analyzed dataset with {row_count} rows.",
            content=content,
            data={"row_count": row_count, "headers": headers, "stats": numeric_stats},
            sources=[],
            next_steps=[
                "Filter by key segment and rerun summary.",
                "Add trend windows if a date column exists.",
            ],
            events=events
            + [
                _event(
                    tool_id=self.metadata.tool_id,
                    event_type="tool_progress",
                    title="Dataset analysis ready",
                    detail=f"Analyzed {len(numeric_stats)} numeric column(s)",
                    data={"numeric_columns": len(numeric_stats)},
                )
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
        delivery_targets = _report_delivery_targets(prompt=prompt, settings=context.settings)
        sanitized_prompt = _redact_delivery_targets(prompt, targets=delivery_targets)
        depth_tier = (
            " ".join(str(context.settings.get("__research_depth_tier") or "standard").split())
            .strip()
            .lower()
            or "standard"
        )
        title = str(params.get("title") or "Executive Report").strip()
        summary_seed = str(params.get("summary") or sanitized_prompt).strip()
        summary = summary_seed or "No summary provided."
        summary = " ".join(summary.split())
        summary = _redact_delivery_targets(summary, targets=delivery_targets)
        if len(summary) > 560:
            summary = f"{summary[:559].rstrip()}..."
        report_intent_flags = _classify_report_intent_with_llm(
            prompt=sanitized_prompt,
            summary=summary,
            title=title,
            settings=context.settings,
        )
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
            requested_focus = _first_sentence(str(params.get("summary") or sanitized_prompt), max_len=260)
            requested_focus = _redact_delivery_targets(requested_focus, targets=delivery_targets)
            location_requested = bool(report_intent_flags.get("location_objective"))
            location_signal = _extract_location_signal_with_llm(finding_excerpt)
            summary_parts: list[str] = []
            if requested_focus:
                summary_parts.append(requested_focus)
            summary_parts.append(f"Captured source analyzed: {finding_title}.")
            if location_requested:
                if location_signal:
                    summary_parts.append(f"Location evidence found: {location_signal}.")
                else:
                    summary_parts.append(
                        "No explicit headquarters/address was confirmed from the captured excerpt; "
                        "inspect Contact/About pages for verified location details."
                    )
            if keyword_line:
                summary_parts.append(f"Observed terms: {keyword_line}.")
            if finding_url:
                summary_parts.append(f"Evidence URL: {finding_url}.")
            if finding_excerpt:
                summary_parts.append(f"Evidence note: {finding_excerpt}")
            summary = " ".join(summary_parts)
        elif bool(report_intent_flags.get("direct_question")) or ("?" in summary):
            direct_answer = _draft_direct_answer(summary)
            if direct_answer:
                summary = direct_answer
        summary = _redact_delivery_targets(summary, targets=delivery_targets)
        if len(summary) > 900:
            summary = f"{summary[:899].rstrip()}..."
        raw_sources = params.get("sources")
        if not isinstance(raw_sources, list):
            raw_sources = context.settings.get("__latest_web_sources")
        source_limit = 80 if depth_tier in {"deep_research", "deep_analytics"} else 24
        source_rows = _normalize_source_rows(raw_sources, limit=source_limit)

        highlights = params.get("highlights")
        if not isinstance(highlights, list):
            highlights = []

        actions = params.get("actions")
        if not isinstance(actions, list):
            actions = []

        highlight_lines = [f"- {str(item).strip()}" for item in highlights if str(item).strip()]
        if not highlight_lines and source_rows:
            highlight_lines = [f"- {line}" for line in _auto_highlights_from_sources(source_rows, limit=8)]
        if not highlight_lines:
            highlight_lines = ["- Key findings will appear here once evidence is synthesized."]
        if depth_tier in {"deep_research", "deep_analytics"} and len(highlight_lines) < 10:
            auto_lines = [f"- {line}" for line in _auto_highlights_from_sources(source_rows, limit=14)]
            for line in auto_lines:
                if line not in highlight_lines:
                    highlight_lines.append(line)
                if len(highlight_lines) >= 14:
                    break

        action_lines = [f"- {str(item).strip()}" for item in actions if str(item).strip()]
        if not action_lines:
            action_lines = [
                "- Validate findings with at least two independent sources before distribution.",
                "- Assign an owner and deadline for each follow-up action item.",
                "- Capture assumptions, risks, and open questions in the final review note.",
            ]

        analysis_paragraphs = _analysis_paragraphs_with_llm(
            title=title,
            summary=summary,
            prompt=sanitized_prompt,
            source_rows=source_rows,
            depth_tier=depth_tier,
        )
        if not analysis_paragraphs:
            analysis_paragraphs = _fallback_analysis_paragraphs(summary=summary)
        analysis_paragraphs = [
            _redact_delivery_targets(item, targets=delivery_targets)
            for item in analysis_paragraphs
            if str(item).strip()
        ]
        reference_lines = _reference_lines(
            source_rows,
            limit=40 if depth_tier in {"deep_research", "deep_analytics"} else 12,
        )
        if not reference_lines:
            reference_lines = ["- No external links were captured for this run."]
        analytics_lines = _analytics_section_lines(context.settings)
        simple_explanation_requested = _prefers_simple_explanation(
            prompt=sanitized_prompt,
            summary=summary,
            title=title,
            settings=context.settings,
            llm_intent_flags=report_intent_flags,
        )
        simple_lines = (
            _simple_explanation_lines(summary=summary, title=title)
            if simple_explanation_requested
            else []
        )

        content = "\n".join(
            [
                f"## {title}",
                "",
                "### Executive Summary",
                summary,
                "",
                *simple_lines,
                *([""] if simple_lines else []),
                "### Detailed Analysis",
                "",
                *analysis_paragraphs[:8],
                *([""] + analytics_lines if analytics_lines else []),
                "",
                "### Highlights",
                *highlight_lines[:14],
                "",
                "### Recommended Next Steps",
                *action_lines[:8],
                "",
                "### Reference Links",
                *reference_lines,
            ]
        )
        content = _redact_delivery_targets(content, targets=delivery_targets)
        context.settings["__latest_report_title"] = title
        context.settings["__latest_report_content"] = content
        if source_rows:
            context.settings["__latest_report_sources"] = source_rows
        return ToolExecutionResult(
            summary=f"Generated report draft: {title}",
            content=content,
            data={
                "title": title,
                "source_count": len(source_rows),
                "research_depth_tier": depth_tier,
                "simple_explanation_included": simple_explanation_requested,
                "analytics_sections_included": bool(analytics_lines),
            },
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
