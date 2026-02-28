from __future__ import annotations

from .models import AnswerBuildContext
from ..text_helpers import compact, extract_first_email


def append_task_understanding(lines: list[str], ctx: AnswerBuildContext) -> None:
    lines.append("## Task Understanding")
    lines.append(f"- Request: {compact(ctx.request.message, 260)}")
    if ctx.request.agent_goal:
        lines.append(f"- Goal: {compact(ctx.request.agent_goal, 240)}")

    rewritten_task = " ".join(
        str(ctx.runtime_settings.get("__task_rewrite_detail") or "").split()
    ).strip()
    if rewritten_task:
        lines.append(f"- Rewritten brief: {compact(rewritten_task, 260)}")

    rewrite_deliverables = ctx.runtime_settings.get("__task_rewrite_deliverables")
    if isinstance(rewrite_deliverables, list):
        cleaned_deliverables = [
            str(item).strip() for item in rewrite_deliverables if str(item).strip()
        ]
        if cleaned_deliverables:
            lines.append(f"- Deliverables: {', '.join(cleaned_deliverables[:6])}")

    rewrite_constraints = ctx.runtime_settings.get("__task_rewrite_constraints")
    if isinstance(rewrite_constraints, list):
        cleaned_constraints = [
            str(item).strip() for item in rewrite_constraints if str(item).strip()
        ]
        if cleaned_constraints:
            lines.append(f"- Constraints: {', '.join(cleaned_constraints[:6])}")

    contract_missing = ctx.runtime_settings.get("__task_clarification_missing")
    if isinstance(contract_missing, list):
        cleaned_missing = [
            str(item).strip() for item in contract_missing if str(item).strip()
        ]
        if cleaned_missing:
            lines.append(f"- Missing requirements: {', '.join(cleaned_missing[:6])}")

    delivery_email = extract_first_email(
        ctx.request.message, ctx.request.agent_goal or ""
    )
    if delivery_email:
        lines.append(f"- Delivery target: `{delivery_email}`")
