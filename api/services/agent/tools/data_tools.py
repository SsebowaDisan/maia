from __future__ import annotations

import csv
import io
from statistics import mean
from typing import Any

from api.services.agent.llm_runtime import call_json_response, call_text_response, env_bool
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)

SCENE_SURFACE_SYSTEM = "system"


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


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _classify_report_intent_with_llm(
    *,
    prompt: str,
    summary: str,
    title: str,
    settings: dict[str, Any],
) -> dict[str, bool]:
    if not env_bool("MAIA_AGENT_LLM_REPORT_INTENT_ENABLED", default=True):
        return {}
    payload = {
        "prompt": " ".join(str(prompt or "").split()).strip()[:520],
        "summary": " ".join(str(summary or "").split()).strip()[:520],
        "title": " ".join(str(title or "").split()).strip()[:200],
        "preferences": settings.get("__user_preferences") if isinstance(settings.get("__user_preferences"), dict) else {},
    }
    response = call_json_response(
        system_prompt=(
            "You classify report-generation intent flags for an agent. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            "{\n"
            '  "location_objective": false,\n'
            '  "direct_question": false,\n'
            '  "simple_explanation_required": false\n'
            "}\n"
            "Rules:\n"
            "- Infer only from provided input.\n"
            "- Do not fabricate facts.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.0,
        timeout_seconds=9,
        max_tokens=120,
    )
    if not isinstance(response, dict):
        return {}
    location_objective = _coerce_bool(response.get("location_objective"))
    direct_question = _coerce_bool(response.get("direct_question"))
    simple_explanation = _coerce_bool(response.get("simple_explanation_required"))
    output: dict[str, bool] = {}
    if location_objective is not None:
        output["location_objective"] = location_objective
    if direct_question is not None:
        output["direct_question"] = direct_question
    if simple_explanation is not None:
        output["simple_explanation_required"] = simple_explanation
    return output


def _extract_location_signal_with_llm(text: str) -> str:
    clean = " ".join(str(text or "").split()).strip()
    if not clean:
        return ""
    if not env_bool("MAIA_AGENT_LLM_LOCATION_SIGNAL_ENABLED", default=True):
        return ""
    response = call_json_response(
        system_prompt=(
            "Extract concrete location evidence from text. Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "location_signal": "string", "has_location_signal": false }\n'
            "Rules:\n"
            "- Keep location_signal empty when no explicit location evidence exists.\n"
            "- Do not infer or guess.\n\n"
            f"Input text:\n{clean[:1200]}"
        ),
        temperature=0.0,
        timeout_seconds=8,
        max_tokens=120,
    )
    if not isinstance(response, dict):
        return ""
    has_location = _coerce_bool(response.get("has_location_signal"))
    signal = " ".join(str(response.get("location_signal") or "").split()).strip(" .,:;")
    if has_location is False:
        return ""
    return signal[:160]


def _draft_direct_answer(question: str) -> str:
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


def _prefers_simple_explanation(
    *,
    prompt: str,
    summary: str,
    title: str,
    settings: dict[str, Any],
    llm_intent_flags: dict[str, bool] | None = None,
) -> bool:
    if bool(settings.get("__simple_explanation_required")):
        return True
    if isinstance(llm_intent_flags, dict) and bool(llm_intent_flags.get("simple_explanation_required")):
        return True
    prefs = settings.get("__user_preferences")
    if not isinstance(prefs, dict):
        prefs = {}
    explicit_pref = _coerce_bool(prefs.get("simple_explanation_required"))
    if explicit_pref is not None:
        return explicit_pref
    inferred = _classify_report_intent_with_llm(
        prompt=prompt,
        summary=summary,
        title=title,
        settings=settings,
    )
    return bool(inferred.get("simple_explanation_required"))


def _normalize_source_rows(raw: Any, *, limit: int = 12) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("snippet") or item.get("excerpt") or "").strip()
        metadata = item.get("metadata")
        if not snippet and isinstance(metadata, dict):
            snippet = str(metadata.get("excerpt") or metadata.get("summary") or "").strip()
        if not label and not url:
            continue
        normalized.append(
            {
                "label": label or url,
                "url": url,
                "snippet": _first_sentence(snippet, max_len=180),
            }
        )
        if len(normalized) >= max(1, int(limit)):
            break
    return normalized


def _analysis_paragraphs_with_llm(
    *,
    title: str,
    summary: str,
    prompt: str,
    source_rows: list[dict[str, str]],
    depth_tier: str,
) -> list[str]:
    if not env_bool("MAIA_AGENT_LLM_REPORT_ANALYSIS_ENABLED", default=True):
        return []
    payload = {
        "title": " ".join(str(title or "").split()).strip()[:220],
        "summary": " ".join(str(summary or "").split()).strip()[:1200],
        "prompt": " ".join(str(prompt or "").split()).strip()[:520],
        "depth_tier": depth_tier,
        "sources_preview": source_rows[:8],
    }
    response = call_json_response(
        system_prompt=(
            "Write concise professional report analysis paragraphs. Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "analysis_paragraphs": ["paragraph one", "paragraph two"] }\n'
            "Rules:\n"
            "- Provide 2-6 clear paragraphs.\n"
            "- Use only provided context; avoid fabrications.\n"
            "- Keep each paragraph between 1-4 sentences.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.2,
        timeout_seconds=12,
        max_tokens=700,
    )
    rows = response.get("analysis_paragraphs") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        return []
    cleaned: list[str] = []
    for item in rows[:6]:
        line = " ".join(str(item or "").split()).strip()
        if not line:
            continue
        cleaned.append(line[:1200])
    return cleaned


def _fallback_analysis_paragraphs(*, summary: str) -> list[str]:
    return [
        (
            "This report expands the initial summary with structured analysis, actionable takeaways, "
            "and source references to support downstream execution decisions."
        ),
        (
            "Use the highlights and recommendations to prioritize next actions, and validate any "
            "high-impact claims against authoritative sources before external distribution."
        ),
        _first_sentence(summary, max_len=260) or "No additional context provided.",
    ]


def _auto_highlights_from_sources(rows: list[dict[str, str]], *, limit: int = 6) -> list[str]:
    output: list[str] = []
    for row in rows:
        label = str(row.get("label") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        if label and snippet:
            output.append(f"{label}: {snippet}")
        elif label:
            output.append(label)
        if len(output) >= max(1, int(limit)):
            break
    return output


def _reference_lines(rows: list[dict[str, str]], *, limit: int = 8) -> list[str]:
    lines: list[str] = []
    for row in rows[: max(1, int(limit))]:
        label = str(row.get("label") or "").strip() or "Source"
        url = str(row.get("url") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        if url:
            line = f"- [{label}]({url})"
        else:
            line = f"- {label}"
        if snippet:
            line = f"{line} - {snippet}"
        lines.append(line)
    return lines


def _analytics_section_lines(settings: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    profile = settings.get("__latest_data_profile")
    if isinstance(profile, dict):
        lines.extend(
            [
                "### Data Profile Snapshot",
                "| Metric | Value |",
                "|---|---|",
                f"| Rows | {int(profile.get('row_count') or 0)} |",
                f"| Columns | {int(profile.get('column_count') or 0)} |",
                f"| Numeric columns | {len(profile.get('numeric_columns') or [])} |",
            ]
        )
        correlations = profile.get("top_correlations")
        if isinstance(correlations, list) and correlations:
            lines.extend(["", "| Strong correlation | Value |", "|---|---|"])
            for item in correlations[:6]:
                if not isinstance(item, dict):
                    continue
                left = " ".join(str(item.get("left") or "").split()).strip()
                right = " ".join(str(item.get("right") or "").split()).strip()
                value = item.get("correlation")
                if not left or not right:
                    continue
                lines.append(f"| {left} vs {right} | {value} |")

    visualization = settings.get("__latest_data_visualization")
    if isinstance(visualization, dict):
        lines.extend(
            [
                "",
                "### Visualization Snapshot",
                "| Field | Value |",
                "|---|---|",
                f"| Chart type | {str(visualization.get('chart_type') or 'n/a')} |",
                f"| Rows plotted | {int(visualization.get('row_count') or 0)} |",
                f"| X axis | {str(visualization.get('x') or 'n/a')} |",
                f"| Y axis | {str(visualization.get('y') or 'n/a')} |",
                f"| Artifact path | {str(visualization.get('path') or 'n/a')} |",
            ]
        )

    ga4_report = settings.get("__latest_analytics_report")
    if isinstance(ga4_report, dict):
        dimensions = ga4_report.get("dimensions")
        metrics = ga4_report.get("metrics")
        lines.extend(
            [
                "",
                "### Analytics API Snapshot",
                "| Metric | Value |",
                "|---|---|",
                f"| Property ID | {str(ga4_report.get('property_id') or 'n/a')} |",
                f"| Rows returned | {int(ga4_report.get('row_count') or 0)} |",
                f"| Dimensions | {', '.join(str(item) for item in (dimensions or [])[:8]) or 'n/a'} |",
                f"| Metrics | {', '.join(str(item) for item in (metrics or [])[:8]) or 'n/a'} |",
            ]
        )
    return lines


def _simple_explanation_lines(*, summary: str, title: str) -> list[str]:
    topic = " ".join(str(title or "").split()).strip() or "this topic"
    first = _first_sentence(summary, max_len=220)
    lines = [
        "### Simple Explanation (For a 5-Year-Old)",
        f"- Imagine **{topic}** is a puzzle. We looked at many pieces and kept the ones that really fit.",
    ]
    if first:
        lines.append(f"- Big idea: {first}")
    lines.append("- Why this helps: when facts fit together, we can make safer and smarter decisions.")
    return lines


def _event(
    *,
    tool_id: str,
    event_type: str,
    title: str,
    detail: str = "",
    data: dict[str, Any] | None = None,
) -> ToolTraceEvent:
    payload = {
        "tool_id": tool_id,
        "scene_surface": SCENE_SURFACE_SYSTEM,
    }
    if isinstance(data, dict):
        payload.update(data)
    return ToolTraceEvent(
        event_type=event_type,
        title=title,
        detail=detail,
        data=payload,
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
        depth_tier = (
            " ".join(str(context.settings.get("__research_depth_tier") or "standard").split())
            .strip()
            .lower()
            or "standard"
        )
        title = str(params.get("title") or "Executive Report").strip()
        summary = str(params.get("summary") or prompt).strip() or "No summary provided."
        summary = " ".join(summary.split())
        if len(summary) > 560:
            summary = f"{summary[:559].rstrip()}..."
        report_intent_flags = _classify_report_intent_with_llm(
            prompt=prompt,
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
            requested_focus = _first_sentence(str(params.get("summary") or prompt), max_len=260)
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
            prompt=prompt,
            source_rows=source_rows,
            depth_tier=depth_tier,
        )
        if not analysis_paragraphs:
            analysis_paragraphs = _fallback_analysis_paragraphs(summary=summary)
        reference_lines = _reference_lines(
            source_rows,
            limit=40 if depth_tier in {"deep_research", "deep_analytics"} else 12,
        )
        if not reference_lines:
            reference_lines = ["- No external links were captured for this run."]
        analytics_lines = _analytics_section_lines(context.settings)
        simple_explanation_requested = _prefers_simple_explanation(
            prompt=prompt,
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
