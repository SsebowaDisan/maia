from __future__ import annotations

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
    unique_next_steps: list[str] = []
    for step in ctx.next_steps:
        cleaned = str(step or "").strip()
        if not cleaned or cleaned in unique_next_steps:
            continue
        unique_next_steps.append(cleaned)

    if not unique_next_steps:
        return

    lines.append("")
    lines.append("## Recommended Next Steps")
    for item in unique_next_steps[:6]:
        lines.append(f"- {item}")
