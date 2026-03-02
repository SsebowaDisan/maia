from __future__ import annotations

from typing import Any

from api.services.agent.tools.web_quality import clamp01, quality_from_render

WEB_TOOL_PREFIXES = ("browser.", "web.", "marketing.web_research")


def is_web_tool(tool_id: str) -> bool:
    text = str(tool_id or "").strip()
    if not text:
        return False
    return text.startswith("browser.") or text.startswith("web.") or text == "marketing.web_research"


def _quality_from_data(data: dict[str, Any]) -> float:
    if "quality_score" in data:
        return clamp01(data.get("quality_score"), default=0.0)
    render_quality = str(data.get("render_quality") or "").strip().lower()
    density = clamp01(data.get("content_density"), default=0.0)
    render_component = quality_from_render(render_quality)
    if render_quality == "blocked":
        return 0.0
    score = (0.65 * render_component) + (0.35 * density)
    return round(clamp01(score, default=0.0), 4)


def record_web_kpi(
    *,
    settings: dict[str, Any],
    tool_id: str,
    status: str,
    duration_seconds: float,
    data: dict[str, Any] | None,
) -> dict[str, Any]:
    metrics = settings.get("__web_kpi")
    if not isinstance(metrics, dict):
        metrics = {
            "web_steps_total": 0,
            "web_steps_success": 0,
            "web_steps_failed": 0,
            "blocked_count": 0,
            "provider_fallback_count": 0,
            "avg_quality_score": 0.0,
            "avg_content_density": 0.0,
            "avg_duration_seconds": 0.0,
            "quality_scores": [],
            "content_densities": [],
            "durations": [],
            "tool_breakdown": {},
        }
    rows = data if isinstance(data, dict) else {}

    metrics["web_steps_total"] = int(metrics.get("web_steps_total") or 0) + 1
    if str(status or "").strip().lower() == "success":
        metrics["web_steps_success"] = int(metrics.get("web_steps_success") or 0) + 1
    else:
        metrics["web_steps_failed"] = int(metrics.get("web_steps_failed") or 0) + 1

    if bool(rows.get("blocked_signal")):
        metrics["blocked_count"] = int(metrics.get("blocked_count") or 0) + 1

    provider_requested = str(rows.get("provider_requested") or "").strip()
    provider_used = str(rows.get("provider") or rows.get("web_provider") or "").strip()
    if provider_requested and provider_used and provider_requested != provider_used:
        metrics["provider_fallback_count"] = int(metrics.get("provider_fallback_count") or 0) + 1

    quality_score = _quality_from_data(rows)
    quality_scores = metrics.get("quality_scores")
    if not isinstance(quality_scores, list):
        quality_scores = []
    quality_scores.append(quality_score)
    metrics["quality_scores"] = quality_scores[-32:]
    if metrics["quality_scores"]:
        total_quality = sum(float(item) for item in metrics["quality_scores"])
        metrics["avg_quality_score"] = round(total_quality / float(len(metrics["quality_scores"])), 4)

    density_value = clamp01(rows.get("content_density"), default=0.0)
    densities = metrics.get("content_densities")
    if not isinstance(densities, list):
        densities = []
    densities.append(density_value)
    metrics["content_densities"] = densities[-32:]
    if metrics["content_densities"]:
        total_density = sum(float(item) for item in metrics["content_densities"])
        metrics["avg_content_density"] = round(total_density / float(len(metrics["content_densities"])), 4)

    durations = metrics.get("durations")
    if not isinstance(durations, list):
        durations = []
    try:
        durations.append(max(0.0, float(duration_seconds)))
    except Exception:
        durations.append(0.0)
    metrics["durations"] = durations[-32:]
    if metrics["durations"]:
        total_duration = sum(float(item) for item in metrics["durations"])
        metrics["avg_duration_seconds"] = round(total_duration / float(len(metrics["durations"])), 3)

    tool_breakdown = metrics.get("tool_breakdown")
    if not isinstance(tool_breakdown, dict):
        tool_breakdown = {}
    current = tool_breakdown.get(tool_id)
    if not isinstance(current, dict):
        current = {"runs": 0, "success": 0, "failed": 0}
    current["runs"] = int(current.get("runs") or 0) + 1
    if str(status or "").strip().lower() == "success":
        current["success"] = int(current.get("success") or 0) + 1
    else:
        current["failed"] = int(current.get("failed") or 0) + 1
    tool_breakdown[tool_id] = current
    metrics["tool_breakdown"] = tool_breakdown

    settings["__web_kpi"] = metrics
    return metrics


def summarize_web_kpi(settings: dict[str, Any]) -> dict[str, Any]:
    metrics = settings.get("__web_kpi")
    if not isinstance(metrics, dict):
        return {
            "web_steps_total": 0,
            "web_steps_success": 0,
            "web_steps_failed": 0,
            "blocked_count": 0,
            "provider_fallback_count": 0,
            "avg_quality_score": 0.0,
            "avg_content_density": 0.0,
            "avg_duration_seconds": 0.0,
            "tool_breakdown": {},
            "ready_for_scale": False,
        }
    total = int(metrics.get("web_steps_total") or 0)
    success = int(metrics.get("web_steps_success") or 0)
    success_rate = (float(success) / float(total)) if total > 0 else 0.0
    avg_quality = clamp01(metrics.get("avg_quality_score"), default=0.0)
    blocked = int(metrics.get("blocked_count") or 0)
    ready_for_scale = bool(total >= 3 and success_rate >= 0.8 and avg_quality >= 0.55 and blocked <= 1)
    return {
        "web_steps_total": total,
        "web_steps_success": success,
        "web_steps_failed": int(metrics.get("web_steps_failed") or 0),
        "blocked_count": blocked,
        "provider_fallback_count": int(metrics.get("provider_fallback_count") or 0),
        "avg_quality_score": round(avg_quality, 4),
        "avg_content_density": round(clamp01(metrics.get("avg_content_density"), default=0.0), 4),
        "avg_duration_seconds": round(max(0.0, float(metrics.get("avg_duration_seconds") or 0.0)), 3),
        "tool_breakdown": dict(metrics.get("tool_breakdown") or {}),
        "ready_for_scale": ready_for_scale,
    }


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def evaluate_web_kpi_gate(
    *,
    settings: dict[str, Any],
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = summary if isinstance(summary, dict) else summarize_web_kpi(settings)
    total = max(0, _as_int(snapshot.get("web_steps_total"), default=0))
    success = max(0, _as_int(snapshot.get("web_steps_success"), default=0))
    blocked = max(0, _as_int(snapshot.get("blocked_count"), default=0))
    fallback_count = max(0, _as_int(snapshot.get("provider_fallback_count"), default=0))
    avg_quality = clamp01(snapshot.get("avg_quality_score"), default=0.0)

    thresholds = {
        "min_steps": max(1, _as_int(settings.get("agent.web_kpi.min_steps"), default=3)),
        "min_success_rate": clamp01(
            settings.get("agent.web_kpi.min_success_rate"),
            default=0.8,
        ),
        "min_avg_quality": clamp01(
            settings.get("agent.web_kpi.min_avg_quality"),
            default=0.55,
        ),
        "max_blocked_count": max(
            0,
            _as_int(settings.get("agent.web_kpi.max_blocked_count"), default=1),
        ),
        "max_provider_fallback_rate": clamp01(
            settings.get("agent.web_kpi.max_provider_fallback_rate"),
            default=0.6,
        ),
    }
    success_rate = (float(success) / float(total)) if total > 0 else 0.0
    fallback_rate = (float(fallback_count) / float(total)) if total > 0 else 0.0

    failed_checks: list[str] = []
    if total < thresholds["min_steps"]:
        failed_checks.append(
            f"insufficient_sample_size(total={total}, required={thresholds['min_steps']})"
        )
    if success_rate < thresholds["min_success_rate"]:
        failed_checks.append(
            (
                "success_rate_below_threshold("
                f"actual={round(success_rate, 3)}, required={thresholds['min_success_rate']})"
            )
        )
    if avg_quality < thresholds["min_avg_quality"]:
        failed_checks.append(
            (
                "quality_below_threshold("
                f"actual={round(avg_quality, 3)}, required={thresholds['min_avg_quality']})"
            )
        )
    if blocked > thresholds["max_blocked_count"]:
        failed_checks.append(
            (
                "blocked_pages_above_threshold("
                f"actual={blocked}, max={thresholds['max_blocked_count']})"
            )
        )
    if fallback_rate > thresholds["max_provider_fallback_rate"]:
        failed_checks.append(
            (
                "provider_fallback_rate_above_threshold("
                f"actual={round(fallback_rate, 3)}, max={thresholds['max_provider_fallback_rate']})"
            )
        )

    ready_for_scale = len(failed_checks) == 0
    gate_enforced = _as_bool(settings.get("agent.web_kpi.enforce_gate"), default=False)
    return {
        "ready_for_scale": ready_for_scale,
        "gate_enforced": gate_enforced,
        "failed_checks": failed_checks,
        "success_rate": round(success_rate, 4),
        "provider_fallback_rate": round(fallback_rate, 4),
        "avg_quality_score": round(avg_quality, 4),
        "thresholds": thresholds,
    }


__all__ = [
    "evaluate_web_kpi_gate",
    "is_web_tool",
    "record_web_kpi",
    "summarize_web_kpi",
]
