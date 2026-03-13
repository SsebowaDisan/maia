from __future__ import annotations

import re

from .models import AnswerBuildContext
from ..text_helpers import compact


def append_verification(lines: list[str], ctx: AnswerBuildContext) -> None:
    if not ctx.verification_report:
        return

    checks = ctx.verification_report.get("checks")
    if not isinstance(checks, list) or not checks:
        return

    score = ctx.verification_report.get("score")
    grade = str(ctx.verification_report.get("grade") or "").strip()
    lines.append("")
    lines.append("## Verification")
    if score is not None:
        lines.append(f"- Quality score: {score}% ({grade or 'n/a'})")
    for check in checks[:8]:
        if not isinstance(check, dict):
            continue
        name = str(check.get("name") or "Check").strip()
        status = str(check.get("status") or "info").strip().upper()
        detail = compact(str(check.get("detail") or ""), 180)
        lines.append(f"- {name} [{status}]: {detail}")


def append_recommended_next_steps(lines: list[str], ctx: AnswerBuildContext) -> None:
    def _is_internal_step(text: str) -> bool:
        clean = str(text or "").strip()
        if not clean:
            return True
        if re.search(r"\b[A-Z][A-Z0-9_]{8,}\b", clean):
            return True
        if re.search(r"`[^`\n]{3,}`", clean):
            return True
        if re.search(r"\bname\s+[A-Za-z_][A-Za-z0-9_]*\s+is\s+not\s+defined\b", clean, flags=re.I):
            return True
        if re.search(r"\b(traceback|exception|stack trace|referenceerror|nameerror)\b", clean, flags=re.I):
            return True
        lowered = clean.lower()
        if re.search(r"\b(?:pip|npm|pnpm|yarn|brew|apt|uv|poetry|playwright)\s+install\b", lowered):
            return True
        if re.search(r"\b(?:set|export)\s+[A-Z][A-Z0-9_]{4,}\b", clean):
            return True
        if re.search(r"\bgoogle_analytics_property_id\b", lowered):
            return True
        if lowered.startswith(("extract specific", "extract key", "analyze collected sources", "set ")):
            return True
        # Filter agent-internal reasoning / implementation notes that can leak from
        # tool next_steps fields (e.g. "semantic understanding constraints",
        # "hardcoded words", "note that the pipeline…").
        if re.search(
            r"\b(semantic\s+understanding|hardcoded\s+word|implementation\s+note|"
            r"pipeline\s+constraint|internal\s+constraint|tool\s+limitation|"
            r"agent\s+reasoning|brain\s+directive|execution\s+context)\b",
            lowered,
        ):
            return True
        if re.match(r"note\s*(?:that|:)\s", lowered):
            return True
        if re.match(r"(?:be\s+aware|please\s+note|important\s*:)\s", lowered):
            return True
        return False

    show_diagnostics = bool(ctx.runtime_settings.get("__show_response_diagnostics"))
    unique_next_steps: list[str] = []
    for step in ctx.next_steps:
        cleaned = str(step or "").strip()
        if not cleaned or cleaned in unique_next_steps:
            continue
        if not show_diagnostics and _is_internal_step(cleaned):
            continue
        unique_next_steps.append(cleaned)

    if not unique_next_steps:
        return

    lines.append("")
    lines.append("## Recommended Next Steps")
    max_items = 6 if show_diagnostics else 3
    for item in unique_next_steps[:max_items]:
        lines.append(f"- {item}")
