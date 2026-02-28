from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_path() -> Path:
    root = Path("logs")
    root.mkdir(parents=True, exist_ok=True)
    return root / "agent_run.log"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _escape_label(value: str) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def _labels(**rows: str) -> str:
    if not rows:
        return ""
    items = [f'{key}="{_escape_label(value)}"' for key, value in sorted(rows.items())]
    return "{" + ",".join(items) + "}"


class AgentObservability:
    def __init__(self) -> None:
        self._lock = Lock()
        self._run_total = 0
        self._needs_human_review_total = 0
        self._plan_steps_by_tool: dict[str, int] = defaultdict(int)
        self._tool_calls: dict[tuple[str, str], int] = defaultdict(int)
        self._tool_duration_sum: dict[str, float] = defaultdict(float)
        self._tool_duration_count: dict[str, int] = defaultdict(int)
        self._llm_calls_by_model: dict[str, int] = defaultdict(int)
        self._llm_prompt_tokens_by_model: dict[str, int] = defaultdict(int)
        self._llm_completion_tokens_by_model: dict[str, int] = defaultdict(int)

    def _write_log(self, *, event: str, payload: dict[str, Any]) -> None:
        row = {
            "timestamp": _utc_now_iso(),
            "event": str(event or "").strip() or "unknown",
            "payload": payload,
        }
        with _log_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=True))
            handle.write("\n")

    def observe_plan_steps(self, *, tool_ids: list[str]) -> None:
        cleaned = [str(item).strip() for item in tool_ids if str(item).strip()]
        if not cleaned:
            return
        with self._lock:
            for tool_id in cleaned:
                self._plan_steps_by_tool[tool_id] += 1
            self._write_log(
                event="plan_steps_selected",
                payload={"tool_ids": cleaned, "count": len(cleaned)},
            )

    def observe_tool_execution(
        self,
        *,
        tool_id: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        clean_tool_id = str(tool_id or "").strip() or "unknown"
        clean_status = str(status or "").strip().lower() or "unknown"
        duration = max(0.0, _safe_float(duration_seconds))
        with self._lock:
            self._tool_calls[(clean_tool_id, clean_status)] += 1
            self._tool_duration_sum[clean_tool_id] += duration
            self._tool_duration_count[clean_tool_id] += 1
            self._write_log(
                event="tool_execution",
                payload={
                    "tool_id": clean_tool_id,
                    "status": clean_status,
                    "duration_seconds": round(duration, 4),
                },
            )

    def observe_llm_usage(
        self,
        *,
        model: str,
        usage: dict[str, Any] | None,
    ) -> None:
        clean_model = str(model or "").strip() or "unknown"
        usage_rows = usage if isinstance(usage, dict) else {}
        prompt_tokens = max(0, _safe_int(usage_rows.get("prompt_tokens"), 0))
        completion_tokens = max(0, _safe_int(usage_rows.get("completion_tokens"), 0))
        with self._lock:
            self._llm_calls_by_model[clean_model] += 1
            self._llm_prompt_tokens_by_model[clean_model] += prompt_tokens
            self._llm_completion_tokens_by_model[clean_model] += completion_tokens
            self._write_log(
                event="llm_usage",
                payload={
                    "model": clean_model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            )

    def observe_run_completion(
        self,
        *,
        run_id: str,
        step_count: int,
        action_count: int,
        source_count: int,
        needs_human_review: bool,
        reward_score: float | None = None,
    ) -> None:
        with self._lock:
            self._run_total += 1
            if needs_human_review:
                self._needs_human_review_total += 1
            self._write_log(
                event="run_completed",
                payload={
                    "run_id": str(run_id or "").strip(),
                    "step_count": max(0, _safe_int(step_count)),
                    "action_count": max(0, _safe_int(action_count)),
                    "source_count": max(0, _safe_int(source_count)),
                    "needs_human_review": bool(needs_human_review),
                    "reward_score": reward_score,
                },
            )

    def prometheus_text(self) -> str:
        with self._lock:
            lines: list[str] = []
            lines.append("# HELP maia_agent_runs_total Total completed agent runs.")
            lines.append("# TYPE maia_agent_runs_total counter")
            lines.append(f"maia_agent_runs_total {self._run_total}")
            lines.append("# HELP maia_agent_needs_human_review_total Runs flagged for human review.")
            lines.append("# TYPE maia_agent_needs_human_review_total counter")
            lines.append(f"maia_agent_needs_human_review_total {self._needs_human_review_total}")

            lines.append("# HELP maia_agent_plan_steps_selected_total Planned steps selected by tool.")
            lines.append("# TYPE maia_agent_plan_steps_selected_total counter")
            for tool_id, count in sorted(self._plan_steps_by_tool.items()):
                lines.append(
                    f"maia_agent_plan_steps_selected_total{_labels(tool_id=tool_id)} {int(count)}"
                )

            lines.append("# HELP maia_agent_tool_calls_total Tool executions by status.")
            lines.append("# TYPE maia_agent_tool_calls_total counter")
            for (tool_id, status), count in sorted(self._tool_calls.items()):
                lines.append(
                    f"maia_agent_tool_calls_total{_labels(tool_id=tool_id, status=status)} {int(count)}"
                )

            lines.append("# HELP maia_agent_tool_duration_seconds_sum Cumulative tool execution duration.")
            lines.append("# TYPE maia_agent_tool_duration_seconds_sum counter")
            for tool_id, value in sorted(self._tool_duration_sum.items()):
                lines.append(
                    f"maia_agent_tool_duration_seconds_sum{_labels(tool_id=tool_id)} {value:.6f}"
                )

            lines.append("# HELP maia_agent_tool_duration_seconds_count Tool execution duration sample count.")
            lines.append("# TYPE maia_agent_tool_duration_seconds_count counter")
            for tool_id, count in sorted(self._tool_duration_count.items()):
                lines.append(
                    f"maia_agent_tool_duration_seconds_count{_labels(tool_id=tool_id)} {int(count)}"
                )

            lines.append("# HELP maia_agent_llm_calls_total LLM calls by model.")
            lines.append("# TYPE maia_agent_llm_calls_total counter")
            for model, count in sorted(self._llm_calls_by_model.items()):
                lines.append(
                    f"maia_agent_llm_calls_total{_labels(model=model)} {int(count)}"
                )

            lines.append("# HELP maia_agent_llm_prompt_tokens_total Prompt tokens consumed by model.")
            lines.append("# TYPE maia_agent_llm_prompt_tokens_total counter")
            for model, count in sorted(self._llm_prompt_tokens_by_model.items()):
                lines.append(
                    f"maia_agent_llm_prompt_tokens_total{_labels(model=model)} {int(count)}"
                )

            lines.append("# HELP maia_agent_llm_completion_tokens_total Completion tokens consumed by model.")
            lines.append("# TYPE maia_agent_llm_completion_tokens_total counter")
            for model, count in sorted(self._llm_completion_tokens_by_model.items()):
                lines.append(
                    f"maia_agent_llm_completion_tokens_total{_labels(model=model)} {int(count)}"
                )

            lines.append("")
            return "\n".join(lines)


_observability: AgentObservability | None = None


def get_agent_observability() -> AgentObservability:
    global _observability
    if _observability is None:
        _observability = AgentObservability()
    return _observability

