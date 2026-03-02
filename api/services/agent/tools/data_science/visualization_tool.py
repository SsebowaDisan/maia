from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)

from .plot_payload import build_interactive_plot_payload
from .quality import (
    _apply_cleaning_steps,
    _missing_dataset_result,
    _plan_cleaning_with_llm,
    _resolve_chart_requirements,
)
from .shared import _as_int, _import_pandas, _limit_rows, _load_dataframe, _trace_event
from .visualization_planner import plan_visualization_with_llm


def _normalize_columns_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
        return [item for item in values if item]
    if isinstance(raw, list):
        values = [" ".join(str(item).split()).strip() for item in raw]
        return [item for item in values if item]
    return []


class DataScienceVisualizationTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="data.science.visualize",
        action_class="draft",
        risk_level="low",
        required_permissions=["analytics.write"],
        execution_policy="auto_execute",
        description="Generate dataset charts for exploratory analysis and reporting.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        prompt_text = " ".join(str(prompt or "").split()).strip()
        events: list[ToolTraceEvent] = []
        df, source_label, warnings, source_ref = _load_dataframe(context=context, params=params)
        if df is None:
            return _missing_dataset_result(warnings, tool_id=self.metadata.tool_id)
        pd = _import_pandas()
        if pd is None:
            return _missing_dataset_result(
                warnings + ["`pandas` is required for this operation but is not installed."],
                tool_id=self.metadata.tool_id,
            )

        max_rows = max(100, min(_as_int(params.get("max_rows"), 30000), 200000))
        df, truncated = _limit_rows(df, max_rows=max_rows)
        chart_type_requested = str(params.get("chart_type") or "auto").strip().lower()
        x_col_requested = str(params.get("x") or "").strip()
        y_col_requested = str(params.get("y") or "").strip()
        y_series_requested = _normalize_columns_list(params.get("y_series"))
        row_count_before_cleaning = int(len(df))
        col_count = int(len(df.columns))
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="prepare_request",
                title="Prepare dataset",
                detail=f"Loaded {row_count_before_cleaning} rows and {col_count} columns",
                data={
                    "row_count": row_count_before_cleaning,
                    "column_count": col_count,
                },
            )
        )

        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="llm.visualization_plan_started",
                title="Plan chart strategy",
                detail="LLM selecting chart type and visual encoding",
                data={
                    "chart_type_requested": chart_type_requested,
                    "x_requested": x_col_requested,
                    "y_requested": y_col_requested,
                },
            )
        )
        llm_viz_plan, llm_visualization_plan_used = plan_visualization_with_llm(
            df=df,
            prompt=prompt_text,
            requested_chart_type=chart_type_requested,
            requested_x=x_col_requested,
            requested_y=y_col_requested,
            requested_y_series=y_series_requested,
        )
        if chart_type_requested in {"", "auto"}:
            chart_type_requested = str(llm_viz_plan.get("chart_type") or "histogram").strip().lower()
        if not x_col_requested:
            x_col_requested = str(llm_viz_plan.get("x") or "").strip()
        if not y_col_requested:
            y_col_requested = str(llm_viz_plan.get("y") or "").strip()
        if not y_series_requested:
            y_series_requested = _normalize_columns_list(llm_viz_plan.get("y_series"))
        llm_title = str(llm_viz_plan.get("title") or "").strip()
        title = str(params.get("title") or llm_title or f"{chart_type_requested.title()} chart").strip()
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="llm.visualization_plan_completed",
                title="Chart strategy ready",
                detail=f"chart={chart_type_requested}, x={x_col_requested or 'auto'}, y={y_col_requested or 'auto'}",
                data={
                    "llm_used": llm_visualization_plan_used,
                    "y_series": y_series_requested[:4],
                    "reasoning": str(llm_viz_plan.get("reasoning") or "")[:220],
                },
            )
        )

        required_columns = [name for name in [x_col_requested, y_col_requested, *y_series_requested] if name]
        required_numeric: list[str] = []
        if chart_type_requested == "scatter":
            required_numeric.extend([name for name in [x_col_requested, y_col_requested] if name])
        elif chart_type_requested in {"line", "bar"}:
            if y_col_requested:
                required_numeric.append(y_col_requested)
            required_numeric.extend(y_series_requested)
        elif chart_type_requested == "histogram":
            if x_col_requested:
                required_numeric.append(x_col_requested)
        required_numeric = list(dict.fromkeys(required_numeric))

        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="llm.dataset_cleaning_started",
                title="Analyze dataset quality",
                detail="LLM planning data cleaning operations",
                data={
                    "chart_type": chart_type_requested,
                    "x": x_col_requested,
                    "y": y_col_requested,
                },
            )
        )
        quality_issues, cleaning_plan, llm_cleaning_used = _plan_cleaning_with_llm(
            df=df,
            chart_type=chart_type_requested,
            x_col=x_col_requested,
            y_col=y_col_requested,
            required_numeric=required_numeric,
            required_columns=required_columns,
        )
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="llm.dataset_cleaning_completed",
                title="Dataset quality analysis complete",
                detail=f"Issues: {len(quality_issues)} | planned steps: {len(cleaning_plan)}",
                data={
                    "issues_count": len(quality_issues),
                    "planned_cleaning_steps": len(cleaning_plan),
                    "llm_used": llm_cleaning_used,
                },
            )
        )

        df, cleaning_applied, cleaning_warnings = _apply_cleaning_steps(
            pd=pd,
            df=df,
            steps=cleaning_plan,
        )
        warnings.extend(cleaning_warnings)
        for step in cleaning_applied:
            events.append(
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="tool_progress",
                    title=f"Clean: {step.get('operation')}",
                    detail=f"Rows {step.get('rows_before')} -> {step.get('rows_after')}",
                    data={
                        "operation": step.get("operation"),
                        "columns": step.get("columns"),
                        "rows_changed": step.get("rows_changed"),
                    },
                )
            )

        chart_type, x_col, y_col, validation_errors, validation_warnings, available_columns = _resolve_chart_requirements(
            pd=pd,
            df=df,
            chart_type=chart_type_requested,
            x_col=x_col_requested,
            y_col=y_col_requested,
        )
        warnings.extend(validation_warnings)
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="normalize_response",
                title="Validate chart request",
                detail=f"chart={chart_type}, x={x_col or 'auto'}, y={y_col or 'auto'}",
                data={
                    "chart_type": chart_type,
                    "x": x_col,
                    "y": y_col,
                    "validation_errors": len(validation_errors),
                },
            )
        )

        if validation_errors:
            content_lines = [
                "### Visualization request needs valid columns",
                f"- Source: {source_label or 'payload'}",
                f"- Requested chart type: {chart_type_requested}",
                "",
                "### Validation issues",
                *[f"- {item}" for item in validation_errors],
                "",
                "### Available columns",
                *[f"- {name}" for name in available_columns[:40]],
            ]
            if quality_issues:
                content_lines.extend(["", "### Data quality issues", *[f"- {item}" for item in quality_issues[:10]]])
            if cleaning_applied:
                content_lines.extend(
                    [
                        "",
                        "### Cleaning applied",
                        *[
                            (
                                f"- {str(step.get('operation') or '')}: "
                                f"rows {step.get('rows_before')} -> {step.get('rows_after')}"
                            )
                            for step in cleaning_applied[:12]
                        ],
                    ]
                )
            events.append(
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="tool_failed",
                    title="Visualization validation failed",
                    detail="Chart columns/types are invalid for the selected chart",
                    data={"validation_errors": validation_errors[:10]},
                )
            )
            return ToolExecutionResult(
                summary="Visualization validation failed.",
                content="\n".join(content_lines),
                data={
                    "available": False,
                    "error_type": "validation",
                    "validation_errors": validation_errors,
                    "available_columns": available_columns,
                    "chart_type_requested": chart_type_requested,
                    "x_requested": x_col_requested,
                    "y_requested": y_col_requested,
                    "y_series_requested": y_series_requested[:6],
                    "quality_issues": quality_issues,
                    "cleaning_plan": cleaning_plan,
                    "cleaning_applied": cleaning_applied,
                    "llm_visualization_plan": llm_viz_plan,
                    "llm_visualization_plan_used": llm_visualization_plan_used,
                    "warnings": warnings,
                },
                sources=[source_ref] if source_ref else [],
                next_steps=[
                    "Select chart columns from the available column list.",
                    "Retry visualization after adjusting `chart_type`, `x`, and `y`.",
                ],
                events=events,
            )

        row_count = int(len(df))
        top_n = max(3, min(_as_int(params.get("top_n"), 12), 40))
        bins = max(5, min(_as_int(params.get("bins"), 20), 120))

        def _is_numeric_column(name: str) -> bool:
            try:
                return bool(pd.api.types.is_numeric_dtype(df[name]))
            except Exception:
                return False

        series_columns: list[str] = []
        if chart_type in {"line", "bar"}:
            for name in [y_col, *y_series_requested]:
                column = str(name or "").strip()
                if not column or column in series_columns or column not in df.columns:
                    continue
                if not _is_numeric_column(column):
                    continue
                series_columns.append(column)
            if y_col and y_col in df.columns and y_col not in series_columns and _is_numeric_column(y_col):
                series_columns.insert(0, y_col)
        elif y_col and y_col in df.columns and _is_numeric_column(y_col):
            series_columns = [y_col]

        interactive_plot = build_interactive_plot_payload(
            df=df,
            chart_type=chart_type,
            title=title,
            x_col=x_col,
            y_col=y_col,
            row_count=row_count,
            series_columns=series_columns,
            top_n=top_n,
            bins=bins,
        )

        out_dir = Path(".maia_agent") / "charts"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        out_path = out_dir / f"data-science-{chart_type}-{stamp}.png"

        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception:
            fallback = out_dir / f"data-science-{chart_type}-{stamp}.txt"
            fallback.write_text(
                f"matplotlib_unavailable\nchart_type={chart_type}\nrows={row_count}",
                encoding="utf-8",
            )
            events.append(
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="api_call_failed",
                    title="Render chart",
                    detail="matplotlib not installed",
                    data={"renderer": "fallback-text"},
                )
            )
            return ToolExecutionResult(
                summary="Visualization fallback file generated.",
                content=(
                    "Matplotlib is unavailable. Created a text fallback artifact.\n"
                    f"- Path: {fallback.resolve()}\n"
                    f"- Chart type requested: {chart_type}"
                ),
                data={
                    "path": str(fallback.resolve()),
                    "chart_type": chart_type,
                    "renderer": "fallback-text",
                    "row_count": row_count,
                    "plot": interactive_plot,
                    "x": x_col,
                    "y": y_col,
                    "y_series": series_columns,
                    "quality_issues": quality_issues,
                    "cleaning_plan": cleaning_plan,
                    "cleaning_applied": cleaning_applied,
                    "llm_visualization_plan": llm_viz_plan,
                    "llm_visualization_plan_used": llm_visualization_plan_used,
                    "rows_before_cleaning": row_count_before_cleaning,
                    "rows_after_cleaning": row_count,
                },
                sources=[source_ref] if source_ref else [],
                next_steps=["Install matplotlib to generate PNG chart artifacts."],
                events=events,
            )

        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="api_call_started",
                title="Render chart",
                detail=f"matplotlib ({chart_type})",
                data={"chart_type": chart_type, "renderer": "matplotlib"},
            )
        )
        fig, ax = plt.subplots(figsize=(10, 5))
        if chart_type == "scatter":
            ax.scatter(df[x_col], df[y_col], alpha=0.75)
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
        elif chart_type == "line":
            active_series = series_columns or ([y_col] if y_col else [])
            if x_col and x_col in df.columns:
                for idx, series_name in enumerate(active_series[:4]):
                    ax.plot(
                        df[x_col],
                        df[series_name],
                        linewidth=2,
                        label=series_name,
                        alpha=max(0.45, 1.0 - idx * 0.12),
                    )
                ax.set_xlabel(x_col)
            else:
                for idx, series_name in enumerate(active_series[:4]):
                    ax.plot(
                        df.index,
                        df[series_name],
                        linewidth=2,
                        label=series_name,
                        alpha=max(0.45, 1.0 - idx * 0.12),
                    )
                ax.set_xlabel("row_index")
            ax.set_ylabel(active_series[0] if active_series else (y_col or "value"))
            if len(active_series) > 1:
                ax.legend(loc="best")
        elif chart_type == "bar":
            grouped = (
                df[[x_col, y_col]]
                .dropna()
                .groupby(x_col)[y_col]
                .mean()
                .sort_values(ascending=False)
                .head(top_n)
            )
            ax.bar(grouped.index.astype(str), grouped.values)
            ax.tick_params(axis="x", rotation=35)
            ax.set_xlabel(x_col)
            ax.set_ylabel(f"avg({y_col})")
        else:
            ax.hist(df[x_col].dropna(), bins=bins, alpha=0.85)
            ax.set_xlabel(x_col)
            ax.set_ylabel("count")
            chart_type = "histogram"

        ax.set_title(title)
        plt.tight_layout()
        fig.savefig(out_path, dpi=140)
        plt.close(fig)
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="api_call_completed",
                title="Render chart completed",
                detail=f"{chart_type} chart saved",
                data={"path": str(out_path.resolve()), "chart_type": chart_type},
            )
        )

        notes = [f"- {item}" for item in warnings[:6]]
        if truncated:
            notes.append(f"- Dataset was truncated to first {row_count_before_cleaning} row(s) before cleaning.")
        if cleaning_applied:
            notes.append(
                f"- Cleaning changed rows from {row_count_before_cleaning} to {row_count}."
            )
        if quality_issues:
            notes.extend([f"- Quality issue: {item}" for item in quality_issues[:6]])

        content_lines = [
            "### Data Visualization",
            f"- Source: {source_label or 'payload'}",
            f"- Chart type: {chart_type}",
            f"- Path: {out_path.resolve()}",
            f"- Rows plotted: {row_count}",
            f"- LLM cleaning planner used: {'yes' if llm_cleaning_used else 'fallback'}",
            f"- LLM visualization planner used: {'yes' if llm_visualization_plan_used else 'fallback'}",
        ]
        if x_col:
            content_lines.append(f"- X column: {x_col}")
        if y_col:
            content_lines.append(f"- Y column: {y_col}")
        if series_columns:
            content_lines.append(f"- Y series: {', '.join(series_columns[:4])}")
        if notes:
            content_lines.extend(["", "### Notes", *notes])

        return ToolExecutionResult(
            summary=f"Generated {chart_type} chart artifact.",
            content="\n".join(content_lines),
            data={
                "path": str(out_path.resolve()),
                "chart_type": chart_type,
                "title": title,
                "row_count": row_count,
                "plot": interactive_plot,
                "x": x_col,
                "y": y_col,
                "y_series": series_columns,
                "renderer": "matplotlib",
                "warnings": warnings,
                "truncated": truncated,
                "quality_issues": quality_issues,
                "cleaning_plan": cleaning_plan,
                "cleaning_applied": cleaning_applied,
                "llm_cleaning_used": llm_cleaning_used,
                "llm_visualization_plan": llm_viz_plan,
                "llm_visualization_plan_used": llm_visualization_plan_used,
                "rows_before_cleaning": row_count_before_cleaning,
                "rows_after_cleaning": row_count,
                "rows_removed_by_cleaning": max(0, row_count_before_cleaning - row_count),
            },
            sources=[source_ref] if source_ref else [],
            next_steps=[
                "Attach this artifact in `report.generate` output.",
                "Run another chart type for additional patterns.",
            ],
            events=events
            + [
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="tool_progress",
                    title="Generate dataset chart",
                    detail=f"{chart_type} chart created",
                    data={"path": str(out_path.resolve()), "chart_type": chart_type},
                )
            ],
        )
