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


def _has_location_prompt(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        token in lowered
        for token in (
            "where",
            "location",
            "located",
            "headquarter",
            "headquarters",
            "address",
            "office",
            "based in",
            "found in",
            "city",
            "country",
        )
    )


def _extract_location_signal(text: str) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        return ""
    patterns = (
        r"\b(?:headquartered|based|located)\s+in\s+([A-Za-z0-9 ,.'()-]{4,80})",
        r"\baddress(?:es)?[:\s]+([A-Za-z0-9 ,.'()#/-]{6,120})",
        r"\b(?:offices?|locations?)\s+(?:in|across)\s+([A-Za-z0-9 ,.'()-]{4,100})",
    )
    for pattern in patterns:
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if not match:
            continue
        value = " ".join(str(match.group(1) or "").split()).strip(" .,:;")
        if value:
            return value
    return ""


def _looks_like_direct_question(text: str) -> bool:
    clean = " ".join(str(text or "").split()).strip().lower()
    if not clean:
        return False
    if "?" in clean:
        return True
    question_starts = (
        "what is ",
        "what are ",
        "how does ",
        "how do ",
        "why ",
        "define ",
        "explain ",
    )
    return any(clean.startswith(prefix) for prefix in question_starts)


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


def _detect_report_topic(*parts: str) -> str:
    combined = " ".join(str(part or "").lower() for part in parts)
    if "machine learning" in combined or "ml " in combined or "ml," in combined:
        return "machine_learning"
    if "headquarter" in combined or "located" in combined or "address" in combined:
        return "location"
    return "general"


def _topic_analysis_paragraphs(*, topic: str, summary: str) -> list[str]:
    if topic == "machine_learning":
        return [
            (
                "Machine learning (ML) is a data-driven approach where statistical models learn "
                "patterns from historical examples and generalize to new inputs. A typical ML "
                "lifecycle includes problem framing, data collection, feature engineering, model "
                "training, validation, deployment, and continuous monitoring."
            ),
            (
                "Core ML paradigms include supervised learning (classification/regression with "
                "labeled data), unsupervised learning (clustering, dimensionality reduction, and "
                "anomaly detection), and reinforcement learning (policy optimization through "
                "reward signals). Teams usually start with simpler baseline models before adopting "
                "higher-complexity architectures."
            ),
            (
                "Common business applications include demand forecasting, fraud detection, "
                "recommendation systems, customer segmentation, predictive maintenance, and "
                "document intelligence. Success depends on clearly defined evaluation metrics "
                "(for example precision/recall, F1, AUC, or RMSE) that match operational outcomes."
            ),
            (
                "Operational risks include data drift, concept drift, bias, limited explainability, "
                "and governance/compliance gaps. Strong production practice includes model versioning, "
                "feature/data quality checks, guardrails for high-risk decisions, and periodic "
                "retraining with post-deployment performance audits."
            ),
        ]
    if topic == "location":
        return [
            (
                "This report focuses on validating location-specific evidence from captured sources. "
                "When location claims are present, they should be grounded in direct, attributable "
                "evidence such as official company pages, filings, or verified profile records."
            ),
            (
                "If location evidence is ambiguous, the recommended path is to collect supporting "
                "signals from contact/about pages and corroborate findings using authoritative external "
                "sources before finalizing any headquarters or address claim."
            ),
        ]
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
            requested_focus = _first_sentence(str(params.get("summary") or prompt), max_len=260)
            location_requested = _has_location_prompt(requested_focus)
            location_signal = _extract_location_signal(finding_excerpt)
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
        elif _looks_like_direct_question(summary):
            direct_answer = _draft_direct_answer(summary)
            if direct_answer:
                summary = direct_answer
        if len(summary) > 900:
            summary = f"{summary[:899].rstrip()}..."
        raw_sources = params.get("sources")
        if not isinstance(raw_sources, list):
            raw_sources = context.settings.get("__latest_web_sources")
        source_rows = _normalize_source_rows(raw_sources, limit=12)

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

        action_lines = [f"- {str(item).strip()}" for item in actions if str(item).strip()]
        if not action_lines:
            action_lines = [
                "- Validate findings with at least two independent sources before distribution.",
                "- Assign an owner and deadline for each follow-up action item.",
                "- Capture assumptions, risks, and open questions in the final review note.",
            ]

        topic = _detect_report_topic(title, summary, prompt)
        analysis_paragraphs = _topic_analysis_paragraphs(topic=topic, summary=summary)
        reference_lines = _reference_lines(source_rows, limit=8)
        if not reference_lines:
            reference_lines = ["- No external links were captured for this run."]

        content = "\n".join(
            [
                f"## {title}",
                "",
                "### Executive Summary",
                summary,
                "",
                "### Detailed Analysis",
                "",
                *analysis_paragraphs[:8],
                "",
                "### Highlights",
                *highlight_lines[:8],
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
            data={"title": title, "source_count": len(source_rows)},
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
