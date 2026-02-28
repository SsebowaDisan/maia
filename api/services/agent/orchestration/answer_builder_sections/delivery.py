from __future__ import annotations

from .models import AnswerBuildContext
from ..constants import DELIVERY_ACTION_IDS
from ..text_helpers import compact, extract_first_email, issue_fix_hint


def append_delivery_status(lines: list[str], ctx: AnswerBuildContext) -> None:
    lines.append("")
    lines.append("## Delivery Status")
    send_actions = [item for item in ctx.actions if item.tool_id in DELIVERY_ACTION_IDS]
    if send_actions:
        latest_send = send_actions[-1]
        status = "sent" if latest_send.status == "success" else "not sent"
        lines.append(f"- Email delivery: {status}.")
        lines.append(f"- Detail: {compact(latest_send.summary, 180)}")
        if latest_send.status != "success":
            hint = issue_fix_hint(latest_send.summary)
            if hint:
                lines.append(f"- Fix: {hint}")
        return

    delivery_email = extract_first_email(
        ctx.request.message, ctx.request.agent_goal or ""
    )
    if delivery_email:
        lines.append("- Email delivery: no send step executed.")
    else:
        lines.append("- No email delivery requested.")


def append_contract_gate(lines: list[str], ctx: AnswerBuildContext) -> None:
    contract_check = ctx.runtime_settings.get("__task_contract_check")
    if not isinstance(contract_check, dict):
        return

    ready_final = bool(contract_check.get("ready_for_final_response"))
    ready_actions = bool(contract_check.get("ready_for_external_actions"))
    missing_items = (
        [
            str(item).strip()
            for item in contract_check.get("missing_items", [])
            if str(item).strip()
        ]
        if isinstance(contract_check.get("missing_items"), list)
        else []
    )
    reason = " ".join(str(contract_check.get("reason") or "").split()).strip()
    lines.append("")
    lines.append("## Contract Gate")
    lines.append(f"- Final response ready: {'yes' if ready_final else 'no'}.")
    lines.append(f"- External actions ready: {'yes' if ready_actions else 'no'}.")
    if missing_items:
        lines.append(f"- Missing items: {', '.join(missing_items[:6])}")
    if reason:
        lines.append(f"- Reason: {compact(reason, 180)}")
