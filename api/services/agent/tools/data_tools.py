from __future__ import annotations

import csv
import io
import re
from statistics import mean
from typing import Any

from api.services.agent.llm_runtime import call_text_response, env_bool
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.orchestration.text_helpers import chunk_preserve_text
from api.services.agent.tools.data_tools_helpers import (
    _analysis_paragraphs_with_llm,
    _analytics_insight_highlights,
    _analytics_insight_paragraphs,
    _analytics_section_lines,
    _annotated_source_lines,
    _as_float,
    _auto_highlights_from_sources,
    _build_evidence_findings_with_llm,
    _classify_report_intent_with_llm,
    _compose_executive_summary,
    _contradiction_section_lines,
    _detect_source_contradictions,
    _draft_report_markdown_with_llm,
    _evidence_findings_markdown,
    _event,
    _extract_location_signal_with_llm,
    _fallback_analysis_paragraphs,
    _first_sentence,
    _normalize_source_rows,
    _prefers_simple_explanation,
    _redact_delivery_targets,
    _reference_lines,
    _recommended_next_steps_with_llm,
    _report_delivery_targets,
    _simple_explanation_lines,
)


def _draft_direct_answer_with_local_llm(question: str) -> str:
    if not env_bool("MAIA_AGENT_LLM_REPORT_QA_ENABLED", default=True):
        return ""
    payload = " ".join(str(question or "").split()).strip()
    if not payload:
        return ""
    response = call_text_response(
        system_prompt=(
            "You answer user questions clearly and concisely for enterprise reports. "
            "Do not mention tools or execution steps."
        ),
        user_prompt=(
            "Provide a direct answer in 2-5 sentences.\n"
            "If confidence is low, state uncertainty briefly.\n\n"
            f"Question:\n{payload}"
        ),
        temperature=0.1,
        timeout_seconds=10,
        max_tokens=260,
    )
    clean = " ".join(str(response or "").split()).strip()
    if not clean:
        return ""
    if len(clean) > 900:
        return f"{clean[:899].rstrip()}..."
    return clean


def _report_has_citation_structure(
    report_text: str,
    *,
    source_count: int,
    requires_temporal_labeling: bool = False,
) -> bool:
    clean = str(report_text or "").strip()
    if not clean:
        return False
    if not re.search(r"(?m)^###\s+Executive Summary\s*$", clean):
        return False
    if not re.search(r"(?m)^##\s+Sources\s*$", clean):
        return False
    if not (
        re.search(r"(?m)^###\s+Detailed Analysis\s*$", clean)
        or re.search(r"(?m)^###\s+Evidence-backed findings\s*$", clean)
        or re.search(r"(?m)^###\s+Key Findings\s*$", clean)
    ):
        return False
    markdown_link_count = len(re.findall(r"\[[^\]]+\]\(https?://[^)]+\)", clean))
    minimum_links = 5 if source_count >= 5 else max(2, source_count)
    if markdown_link_count < minimum_links:
        return False
    lowered = clean.lower()
    if not (("why it matters" in lowered) or ("plain-language" in lowered) or ("in practice" in lowered)):
        return False
    cited_finding_bullets = len(re.findall(r"(?m)^- .*\[[^\]]+\]\(https?://[^)]+\)", clean))
    if source_count >= 3 and cited_finding_bullets < 3:
        return False
    if requires_temporal_labeling and not re.search(r"(?i)(foundational|validation):\s*(?:19|20)\d{2}", clean):
        return False
    return True

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
            direct_answer = _draft_direct_answer_with_local_llm(summary)
            if direct_answer:
                summary = direct_answer
        summary = _redact_delivery_targets(summary, targets=delivery_targets)
        if len(summary) > 900:
            summary = f"{summary[:899].rstrip()}..."
        raw_sources = params.get("sources")
        if not isinstance(raw_sources, list):
            raw_sources = context.settings.get("__latest_web_sources")
        source_limit = 320 if depth_tier in {"deep_research", "deep_analytics"} else 120
        source_rows = _normalize_source_rows(raw_sources, limit=source_limit)
        task_contract = context.settings.get("__task_contract")
        required_facts = (
            [
                " ".join(str(item or "").split()).strip()
                for item in task_contract.get("required_facts", [])
                if " ".join(str(item or "").split()).strip()
            ]
            if isinstance(task_contract, dict) and isinstance(task_contract.get("required_facts"), list)
            else []
        )
        contract_outputs = (
            [
                " ".join(str(item or "").split()).strip()
                for item in task_contract.get("required_outputs", [])
                if " ".join(str(item or "").split()).strip()
            ]
            if isinstance(task_contract, dict) and isinstance(task_contract.get("required_outputs"), list)
            else []
        )
        requires_temporal_labeling = any(
            marker in " ".join([sanitized_prompt, summary, *contract_outputs]).lower()
            for marker in (
                "foundational",
                "validation",
                "source era",
                "era (",
            )
        )
        summary = _compose_executive_summary(
            title=title,
            summary=summary,
            prompt=sanitized_prompt,
            source_rows=source_rows,
            depth_tier=depth_tier,
        )
        evidence_findings = _build_evidence_findings_with_llm(
            title=title,
            prompt=sanitized_prompt,
            source_rows=source_rows,
            depth_tier=depth_tier,
            required_facts=required_facts,
        )
        evidence_findings_block = _evidence_findings_markdown(evidence_findings, source_rows)
        annotated_source_lines = _annotated_source_lines(
            source_rows,
            limit=7 if depth_tier in {"deep_research", "deep_analytics", "expert"} else 6,
        )
        annotated_sources_block = (
            "\n".join(["## Sources", "", *annotated_source_lines]).strip()
            if annotated_source_lines
            else ""
        )

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
            analytics_highlights = _analytics_insight_highlights(context.settings)
            if analytics_highlights:
                highlight_lines = [f"- {line}" for line in analytics_highlights]
        if not highlight_lines:
            highlight_lines = [
                "- Evidence synthesis is currently limited; additional validated sources will increase confidence."
            ]
        if depth_tier in {"deep_research", "deep_analytics"} and len(highlight_lines) < 10:
            auto_lines = [f"- {line}" for line in _auto_highlights_from_sources(source_rows, limit=14)]
            for line in auto_lines:
                if line not in highlight_lines:
                    highlight_lines.append(line)
                if len(highlight_lines) >= 14:
                    break

        action_lines = [f"- {str(item).strip()}" for item in actions if str(item).strip()]
        if not action_lines:
            llm_next_steps = _recommended_next_steps_with_llm(
                title=title,
                prompt=sanitized_prompt,
                summary=summary,
                source_rows=source_rows,
                depth_tier=depth_tier,
            )
            action_lines = [f"- {item}" for item in llm_next_steps if str(item).strip()]
        if not action_lines:
            action_lines = [
                f"- Validate unresolved claims in {title} with additional primary sources.",
                "- Confirm decision-impacting facts with source-level verification before distribution.",
                "- Finalize owner, timeline, and success criteria for each follow-up action.",
            ]

        analysis_paragraphs = _analysis_paragraphs_with_llm(
            title=title,
            summary=summary,
            prompt=sanitized_prompt,
            source_rows=source_rows,
            depth_tier=depth_tier,
        )
        if not source_rows:
            analytics_paragraphs = _analytics_insight_paragraphs(context.settings)
            if analytics_paragraphs:
                analysis_paragraphs = analytics_paragraphs
        if not analysis_paragraphs:
            analysis_paragraphs = _fallback_analysis_paragraphs(
                summary=summary,
                prompt=sanitized_prompt,
                title=title,
                source_rows=source_rows,
                depth_tier=depth_tier,
            )
        analysis_paragraphs = [
            _redact_delivery_targets(item, targets=delivery_targets)
            for item in analysis_paragraphs
            if str(item).strip()
        ]
        analysis_lines: list[str] = []
        for idx, paragraph in enumerate(analysis_paragraphs):
            text = " ".join(str(paragraph or "").split()).strip()
            if not text:
                continue
            analysis_lines.append(text)
            if idx < (len(analysis_paragraphs) - 1):
                analysis_lines.append("")
        reference_lines = _reference_lines(
            source_rows,
            limit=max(12, len(source_rows)),
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

        contradiction_lines: list[str] = []
        if depth_tier in {"deep_research", "deep_analytics", "expert"} and source_rows:
            conflicts = _detect_source_contradictions(source_rows, topic=title)
            contradiction_lines = _contradiction_section_lines(conflicts)

        llm_report = _draft_report_markdown_with_llm(
            title=title,
            prompt=sanitized_prompt,
            summary=summary,
            source_rows=source_rows,
            evidence_findings_block=evidence_findings_block,
            annotated_sources_block=annotated_sources_block,
            required_facts=required_facts,
            analysis_paragraphs=analysis_paragraphs,
            highlight_lines=highlight_lines,
            action_lines=action_lines,
            analytics_lines=analytics_lines,
            contradiction_lines=contradiction_lines,
            depth_tier=depth_tier,
        )

        fallback_content = "\n".join(
            [
                f"## {title}",
                "",
                "### Executive Summary",
                summary,
                "",
                *simple_lines,
                *([""] if simple_lines else []),
                *(evidence_findings_block.splitlines() + [""] if evidence_findings_block else []),
                "### Detailed Analysis",
                "",
                *analysis_lines,
                *([""] + analytics_lines if analytics_lines else []),
                *([""] + contradiction_lines if contradiction_lines else []),
                "",
                "### Highlights",
                *highlight_lines[:14],
                "",
                "### Recommended Next Steps",
                *action_lines[:32],
                "",
                *(annotated_sources_block.splitlines() if annotated_sources_block else ["## Sources", *reference_lines]),
            ]
        )
        content = (
            llm_report
            if _report_has_citation_structure(
                llm_report,
                source_count=len(source_rows),
                requires_temporal_labeling=requires_temporal_labeling,
            )
            else fallback_content
        )
        content = _redact_delivery_targets(content, targets=delivery_targets)
        context.settings["__latest_report_title"] = title
        context.settings["__latest_report_content"] = content
        if source_rows:
            context.settings["__latest_report_sources"] = source_rows
        body_chunks = chunk_preserve_text(
            content,
            chunk_size=180,
            limit=max(1, (len(content) // 180) + 2),
        )
        report_events = [
            ToolTraceEvent(
                event_type="doc_open",
                title="Open report template",
                detail=f"Preparing report draft: {title}",
                data={"title": title},
            ),
        ]
        typed_preview = ""
        for chunk_index, chunk in enumerate(body_chunks, start=1):
            typed_preview += chunk
            report_events.append(
                ToolTraceEvent(
                    event_type="doc_type_text",
                    title=f"Writing report {chunk_index}/{len(body_chunks)}",
                    detail=chunk or " ",
                    data={
                        "title": title,
                        "chunk_index": chunk_index,
                        "chunk_total": len(body_chunks),
                        "typed_preview": typed_preview,
                    },
                )
            )
        report_events.append(
            ToolTraceEvent(
                event_type="doc_insert_text",
                title="Populate report sections",
                detail="Filled summary, highlights, and action plan sections",
                data={"title": title, "typed_preview": content},
            )
        )
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
            events=report_events,
        )
