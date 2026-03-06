from __future__ import annotations

from .models import AnswerBuildContext
from ..constants import DELIVERY_ACTION_IDS
from ..text_helpers import compact, extract_first_email, issue_fix_hint

EXTERNAL_ACTION_TOOL_IDS = (
    *DELIVERY_ACTION_IDS,
    "browser.contact_form.send",
    "slack.post_message",
)


def _required_external_actions(ctx: AnswerBuildContext) -> list[str]:
    contract = ctx.runtime_settings.get("__task_contract")
    if not isinstance(contract, dict):
        return []
    raw = contract.get("required_actions")
    if not isinstance(raw, list):
        return []
    wanted = {"send_email", "submit_contact_form", "post_message"}
    return [
        str(item).strip()
        for item in raw
        if str(item).strip() in wanted
    ][:4]


def append_delivery_status(lines: list[str], ctx: AnswerBuildContext) -> None:
    lines.append("")
    lines.append("## Delivery Status")
    send_actions = [item for item in ctx.actions if item.tool_id in EXTERNAL_ACTION_TOOL_IDS]
    if send_actions:
        latest_send = send_actions[-1]
        status = "completed" if latest_send.status == "success" else "not completed"
        lines.append(f"- External action: {status}.")
        lines.append(f"- Tool: `{latest_send.tool_id}`.")
        lines.append(f"- Detail: {compact(latest_send.summary, 180)}")
        if latest_send.status != "success":
            hint = issue_fix_hint(latest_send.summary)
            if hint:
                lines.append(f"- Fix: {hint}")
        return

    required_external_actions = _required_external_actions(ctx)
    if required_external_actions:
        lines.append(f"- Required external actions: {', '.join(required_external_actions)}.")
        lines.append("- Status: no successful external action was recorded in this run.")
        return

    delivery_email = extract_first_email(
        ctx.request.message, ctx.request.agent_goal or ""
    )
    if delivery_email:
        lines.append("- Email delivery requested but no send step executed.")
    else:
        lines.append("- No external delivery action requested.")


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
