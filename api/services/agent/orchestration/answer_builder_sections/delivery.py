from __future__ import annotations

from .models import AnswerBuildContext
from ..constants import DELIVERY_ACTION_IDS
from ..text_helpers import compact, extract_first_email, issue_fix_hint

EXTERNAL_ACTION_TOOL_IDS = (
    *DELIVERY_ACTION_IDS,
    "browser.contact_form.send",
    "slack.post_message",
)
EXTERNAL_ACTION_TOOL_MAP = {
    "send_email": {"gmail.send", "email.send", "mailer.report_send"},
    "submit_contact_form": {"browser.contact_form.send"},
    "post_message": {"slack.post_message"},
}


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


def _external_action_contract_status(ctx: AnswerBuildContext) -> tuple[bool | None, str]:
    contract_check = ctx.runtime_settings.get("__task_contract_check")
    if not isinstance(contract_check, dict):
        return None, ""
    ready_actions = bool(contract_check.get("ready_for_external_actions"))
    reason = compact(str(contract_check.get("reason") or ""), 180)
    return ready_actions, reason


def _normalize_side_effect_status(value: Any) -> str:
    cleaned = " ".join(str(value or "").split()).strip().lower()
    if cleaned in {"completed", "success", "sent"}:
        return "completed"
    if cleaned in {"failed", "blocked", "pending"}:
        return cleaned
    return ""


def _truth_ledger_rows(ctx: AnswerBuildContext, *, ready_actions: bool | None) -> list[str]:
    side_effect_raw = ctx.runtime_settings.get("__side_effect_status")
    side_effect_status = dict(side_effect_raw) if isinstance(side_effect_raw, dict) else {}
    required_external_actions = _required_external_actions(ctx)
    observed_keys = [
        key
        for key in side_effect_status.keys()
        if str(key).strip() in {"send_email", "submit_contact_form", "post_message"}
    ]
    ordered_keys: list[str] = []
    for key in [*required_external_actions, *observed_keys]:
        normalized = str(key or "").strip()
        if not normalized or normalized in ordered_keys:
            continue
        ordered_keys.append(normalized)

    handoff_state_raw = ctx.runtime_settings.get("__handoff_state")
    handoff_state = dict(handoff_state_raw) if isinstance(handoff_state_raw, dict) else {}
    resumed = " ".join(str(handoff_state.get("state") or "").split()).strip().lower() == "resumed"
    rows: list[str] = []
    for action_key in ordered_keys[:4]:
        mapped_tools = EXTERNAL_ACTION_TOOL_MAP.get(action_key, set())
        row_raw = side_effect_status.get(action_key)
        row = dict(row_raw) if isinstance(row_raw, dict) else {}
        side_effect_status_value = _normalize_side_effect_status(row.get("status"))
        latest_action = next(
            (item for item in reversed(ctx.actions) if item.tool_id in mapped_tools),
            None,
        )
        attempted = bool(row) or latest_action is not None
        blocked = side_effect_status_value == "blocked"
        if attempted and not blocked and ready_actions is False and side_effect_status_value in {"completed", "failed"}:
            blocked = True
        approved = attempted and side_effect_status_value not in {"pending", ""}
        sent = side_effect_status_value == "completed" and not blocked
        rows.append(
            (
                f"- `{action_key}`: attempted={'yes' if attempted else 'no'}, "
                f"approved={'yes' if approved else 'no'}, "
                f"blocked={'yes' if blocked else 'no'}, "
                f"resumed={'yes' if resumed else 'no'}, "
                f"sent={'yes' if sent else 'no'}."
            )
        )
    return rows


def append_delivery_status(lines: list[str], ctx: AnswerBuildContext) -> None:
    lines.append("")
    lines.append("## Delivery Status")
    send_actions = [item for item in ctx.actions if item.tool_id in EXTERNAL_ACTION_TOOL_IDS]
    ready_actions, gate_reason = _external_action_contract_status(ctx)
    truth_rows = _truth_ledger_rows(ctx, ready_actions=ready_actions)
    if truth_rows:
        lines.append("- Truthfulness ledger:")
        lines.extend(truth_rows)
    if send_actions:
        latest_send = send_actions[-1]
        gate_blocks_success = latest_send.status == "success" and ready_actions is False
        status = "completed" if latest_send.status == "success" and not gate_blocks_success else "not completed"
        lines.append(f"- External action: {status}.")
        if latest_send.status == "success" and not gate_blocks_success:
            lines.append("- External action attempt: executed successfully.")
        elif gate_blocks_success:
            lines.append("- External action attempt: executed but blocked by contract gate.")
        else:
            lines.append("- External action attempt: executed but failed.")
        lines.append(f"- Tool: `{latest_send.tool_id}`.")
        lines.append(f"- Detail: {compact(latest_send.summary, 180)}")
        if gate_blocks_success and gate_reason:
            lines.append(f"- Contract gate reason: {gate_reason}")
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
