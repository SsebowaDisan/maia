from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)


class ChartGenerateTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="analytics.chart.generate",
        action_class="draft",
        risk_level="low",
        required_permissions=["analytics.write"],
        execution_policy="auto_execute",
        description="Generate chart PNG files from provided data points.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        title = str(params.get("title") or "KPI Chart").strip()
        labels = params.get("labels")
        values = params.get("values")
        if not isinstance(labels, list) or not isinstance(values, list) or len(labels) != len(values):
            labels = ["A", "B", "C"]
            values = [1, 2, 3]

        safe_labels = [str(item) for item in labels[:50]]
        safe_values: list[float] = []
        for item in values[:50]:
            try:
                safe_values.append(float(item))
            except (TypeError, ValueError):
                safe_values.append(0.0)

        out_dir = Path(".maia_agent") / "charts"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        out_file = out_dir / f"chart-{stamp}.png"

        used_matplotlib = False
        try:
            import matplotlib.pyplot as plt

            plt.figure(figsize=(10, 5))
            plt.plot(safe_labels, safe_values, marker="o", linewidth=2)
            plt.title(title)
            plt.xticks(rotation=35, ha="right")
            plt.tight_layout()
            plt.savefig(out_file, dpi=140)
            plt.close()
            used_matplotlib = True
        except Exception:
            # Keep deterministic fallback output text if matplotlib is unavailable.
            out_file = out_dir / f"chart-{stamp}.txt"
            lines = [f"{label}: {value}" for label, value in zip(safe_labels, safe_values)]
            out_file.write_text("\n".join(lines), encoding="utf-8")

        return ToolExecutionResult(
            summary=f"Generated {'PNG chart' if used_matplotlib else 'chart data file'}: {out_file.name}",
            content=(
                f"Generated chart artifact for `{title}`.\n"
                f"- Path: {out_file.resolve()}\n"
                f"- Points: {len(safe_values)}\n"
                f"- Renderer: {'matplotlib' if used_matplotlib else 'fallback-text'}"
            ),
            data={
                "path": str(out_file.resolve()),
                "title": title,
                "points": len(safe_values),
                "renderer": "matplotlib" if used_matplotlib else "fallback-text",
            },
            sources=[],
            next_steps=[
                "Attach chart artifact in Docs/Slides reporting flow.",
                "Track chart over time with periodic data snapshots.",
            ],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Generate chart artifact",
                    detail=title,
                    data={"points": len(safe_values)},
                )
            ],
        )

