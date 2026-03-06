from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
)

from .quality import _missing_dataset_result, _plan_dataset_cleaning_with_llm
from .shared import _as_int, _limit_rows, _load_dataframe, _trace_event


class DataScienceProfileTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="data.science.profile",
        action_class="read",
        risk_level="medium",
        required_permissions=["data.read"],
        execution_policy="auto_execute",
        description="Profile datasets for quality checks, summary stats, and correlations.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        del prompt
        events = []
        df, source_label, warnings, source_ref = _load_dataframe(context=context, params=params)
        if df is None:
            return _missing_dataset_result(
                warnings,
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )

        max_rows = max(100, min(_as_int(params.get("max_rows"), 20000), 200000))
        df, truncated = _limit_rows(df, max_rows=max_rows)
        row_count = int(len(df))
        col_count = int(len(df.columns))
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="prepare_request",
                title="Prepare dataset",
                detail=f"Loaded {row_count} rows and {col_count} columns",
                data={"row_count": row_count, "column_count": col_count},
            )
        )
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="llm.dataset_cleaning_started",
                title="Analyze dataset quality",
                detail="LLM identifies quality issues and cleanup recommendations",
                data={"workflow": "profiling"},
            )
        )
        quality_issues, cleaning_plan, llm_cleaning_used = _plan_dataset_cleaning_with_llm(
            df=df,
            workflow="profiling",
            required_numeric=[],
            required_columns=[],
            context_payload={"source": source_label or "payload"},
        )
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="llm.dataset_cleaning_completed",
                title="Dataset quality analysis complete",
                detail=f"Issues: {len(quality_issues)} | suggested steps: {len(cleaning_plan)}",
                data={
                    "issues_count": len(quality_issues),
                    "suggested_steps": len(cleaning_plan),
                    "llm_used": llm_cleaning_used,
                },
            )
        )
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="api_call_started",
                title="Compute profile statistics",
                detail="Summarizing schema, missingness, and correlations",
                data={"operation": "dataset_profile"},
            )
        )

        column_stats: list[dict[str, Any]] = []
        for column in df.columns:
            series = df[column]
            missing = int(series.isna().sum())
            missing_pct = (missing / row_count * 100.0) if row_count else 0.0
            column_stats.append(
                {
                    "column": column,
                    "dtype": str(series.dtype),
                    "missing": missing,
                    "missing_pct": round(missing_pct, 2),
                    "unique": int(series.nunique(dropna=True)),
                }
            )

        numeric_df = df.select_dtypes(include="number")
        numeric_columns = list(numeric_df.columns)
        numeric_summary: dict[str, dict[str, float]] = {}
        for column in numeric_columns:
            series = numeric_df[column].dropna()
            if series.empty:
                continue
            numeric_summary[column] = {
                "min": float(series.min()),
                "mean": float(series.mean()),
                "median": float(series.median()),
                "max": float(series.max()),
            }

        top_correlations: list[dict[str, Any]] = []
        if len(numeric_columns) >= 2:
            corr = numeric_df.corr(numeric_only=True)
            for idx, left in enumerate(numeric_columns):
                for right in numeric_columns[idx + 1 :]:
                    try:
                        score = float(corr.loc[left, right])
                    except Exception:
                        continue
                    top_correlations.append(
                        {
                            "left": left,
                            "right": right,
                            "correlation": round(score, 4),
                            "abs_correlation": round(abs(score), 4),
                        }
                    )
            top_correlations.sort(key=lambda item: item["abs_correlation"], reverse=True)
            top_correlations = top_correlations[:8]
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="api_call_completed",
                title="Compute profile statistics completed",
                detail=f"Profiled {len(column_stats)} columns",
                data={
                    "column_stats": len(column_stats),
                    "numeric_columns": len(numeric_columns),
                    "top_correlations": len(top_correlations),
                },
            )
        )
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="normalize_response",
                title="Normalize profile output",
                detail=f"rows={row_count}, columns={col_count}",
                data={"row_count": row_count, "column_count": col_count},
            )
        )

        summary_lines = [
            f"- {name}: mean {item['mean']:.4f}, median {item['median']:.4f}, min {item['min']:.4f}, max {item['max']:.4f}"
            for name, item in list(numeric_summary.items())[:8]
        ]
        correlation_lines = [
            f"- {item['left']} vs {item['right']}: {item['correlation']:.4f}"
            for item in top_correlations[:6]
        ]
        notes = [f"- {item}" for item in warnings[:6]]
        if truncated:
            notes.append(f"- Dataset was truncated to first {row_count} row(s).")

        content_lines = [
            "### Data Science Profile",
            f"- Source: {source_label or 'payload'}",
            f"- Rows analyzed: {row_count}",
            f"- Columns: {col_count}",
            f"- Numeric columns: {len(numeric_columns)}",
            "",
            "### Numeric Summary",
            *(summary_lines or ["- No numeric columns detected."]),
            "",
            "### Strongest Correlations",
            *(correlation_lines or ["- Not enough numeric columns for correlation analysis."]),
        ]
        if quality_issues:
            content_lines.extend(["", "### Data Quality Issues", *[f"- {item}" for item in quality_issues[:10]]])
        if cleaning_plan:
            content_lines.extend(
                [
                    "",
                    "### Suggested Cleaning Plan",
                    *[
                        (
                            f"- {str(step.get('operation') or '')}: "
                            f"{str(step.get('reason') or 'No reason provided.')}"
                        )
                        for step in cleaning_plan[:10]
                    ],
                ]
            )
        if notes:
            content_lines.extend(["", "### Notes", *notes])

        context.settings["__latest_data_profile"] = {
            "source": source_label,
            "row_count": row_count,
            "column_count": col_count,
            "numeric_columns": numeric_columns[:24],
            "top_correlations": top_correlations[:8],
            "quality_issues": quality_issues[:10],
        }

        return ToolExecutionResult(
            summary=f"Profiled dataset with {row_count} rows and {col_count} columns.",
            content="\n".join(content_lines),
            data={
                "source": source_label,
                "row_count": row_count,
                "column_count": col_count,
                "column_stats": column_stats,
                "numeric_columns": numeric_columns,
                "numeric_summary": numeric_summary,
                "top_correlations": top_correlations,
                "truncated": truncated,
                "warnings": warnings,
                "quality_issues": quality_issues,
                "cleaning_plan": cleaning_plan,
                "llm_cleaning_used": llm_cleaning_used,
            },
            sources=[source_ref] if source_ref else [],
            next_steps=[
                "Use `data.science.visualize` for exploratory charts.",
                "Use `data.science.ml.train` with `target` for predictive modeling.",
            ],
            events=events
            + [
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="tool_progress",
                    title="Dataset profile ready",
                    detail=f"{len(column_stats)} columns profiled",
                    data={"column_stats": len(column_stats)},
                )
            ],
        )
