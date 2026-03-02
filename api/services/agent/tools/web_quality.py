from __future__ import annotations

from typing import Any


def clamp01(value: Any, *, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        numeric = float(default)
    if numeric < 0.0:
        return 0.0
    if numeric > 1.0:
        return 1.0
    return numeric


def quality_from_render(render_quality: str) -> float:
    normalized = str(render_quality or "").strip().lower()
    if normalized == "high":
        return 1.0
    if normalized == "medium":
        return 0.7
    if normalized == "low":
        return 0.35
    if normalized == "blocked":
        return 0.0
    return 0.5


def compute_quality_score(
    *,
    render_quality: str,
    content_density: Any,
    extraction_confidence: Any,
    schema_coverage: Any,
    evidence_count: Any,
    blocked_signal: Any,
) -> float:
    render_component = quality_from_render(render_quality)
    density_component = clamp01(content_density, default=0.0)
    confidence_component = clamp01(extraction_confidence, default=0.0)
    coverage_component = clamp01(schema_coverage, default=0.0)
    try:
        evidence_numeric = float(evidence_count)
    except Exception:
        evidence_numeric = 0.0
    evidence_component = clamp01(evidence_numeric / 6.0, default=0.0)

    blocked_penalty = 0.0
    if bool(blocked_signal):
        blocked_penalty = 0.55

    score = (
        (0.30 * render_component)
        + (0.20 * density_component)
        + (0.25 * confidence_component)
        + (0.20 * coverage_component)
        + (0.05 * evidence_component)
        - blocked_penalty
    )
    return round(clamp01(score, default=0.0), 4)


def quality_band(score: Any) -> str:
    numeric = clamp01(score, default=0.0)
    if numeric >= 0.8:
        return "high"
    if numeric >= 0.55:
        return "medium"
    if numeric >= 0.3:
        return "low"
    return "blocked"


def quality_remediation(*, score: Any, blocked_signal: Any) -> list[str]:
    numeric = clamp01(score, default=0.0)
    if bool(blocked_signal):
        return [
            "Target page appears challenged/blocked. Retry with an alternate source URL.",
            "If possible, provide direct page text/HTML for deterministic extraction.",
        ]
    if numeric < 0.3:
        return [
            "Extraction quality is poor. Retry capture with a more specific URL.",
            "Add a second source and compare overlapping facts before delivery.",
        ]
    if numeric < 0.55:
        return [
            "Extraction quality is limited. Validate key fields against another source.",
        ]
    return []


__all__ = [
    "clamp01",
    "compute_quality_score",
    "quality_band",
    "quality_from_render",
    "quality_remediation",
]
