from __future__ import annotations

import json
from collections.abc import Callable, Generator
from typing import Any

from api.services.agent.llm_contracts import verify_task_contract_fulfillment
from api.services.agent.models import AgentAction, AgentActivityEvent, AgentSource
from api.services.agent.planner import LLM_ALLOWED_TOOL_IDS, PlannedStep
from api.services.agent.tools.base import ToolExecutionContext


def action_rows_for_contract_check(actions: list[AgentAction]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for action in actions[-24:]:
        rows.append(
            {
                "tool_id": action.tool_id,
                "status": action.status,
                "summary": action.summary,
                "metadata": action.metadata if isinstance(action.metadata, dict) else {},
            }
        )
    return rows


def source_rows_for_contract_check(sources: list[AgentSource]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources[:24]:
        rows.append(
            {
                "label": str(source.label or "").strip(),
                "url": str(source.url or "").strip(),
                "score": source.score,
                "metadata": source.metadata if isinstance(source.metadata, dict) else {},
            }
        )
    return rows


def run_contract_check_live(
    *,
    run_id: str,
    phase: str,
    task_contract: dict[str, Any],
    request_message: str,
    execution_context: ToolExecutionContext,
    executed_steps: list[dict[str, Any]],
    actions: list[AgentAction],
    sources: list[AgentSource],
    pending_action_tool_id: str = "",
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    check_started = activity_event_factory(
        event_type="llm.delivery_check_started",
        title="Verifying task contract",
        detail=f"Contract check phase: {phase}",
        metadata={"phase": phase},
    )
    yield emit_event(check_started)
    report_body = str(execution_context.settings.get("__latest_report_content") or "").strip()
    check = verify_task_contract_fulfillment(
        contract=task_contract,
        request_message=request_message,
        executed_steps=executed_steps,
        actions=action_rows_for_contract_check(actions),
        report_body=report_body,
        sources=source_rows_for_contract_check(sources),
        allowed_tool_ids=sorted(list(LLM_ALLOWED_TOOL_IDS)),
        pending_action_tool_id=pending_action_tool_id,
    )
    execution_context.settings["__task_contract_check"] = check
    missing = (
        [str(item).strip() for item in check.get("missing_items", []) if str(item).strip()]
        if isinstance(check.get("missing_items"), list)
        else []
    )
    ready_final = bool(check.get("ready_for_final_response"))
    ready_actions = bool(check.get("ready_for_external_actions"))
    if ready_final and ready_actions:
        check_completed = activity_event_factory(
            event_type="llm.delivery_check_completed",
            title="Task contract satisfied",
            detail="Run is ready for final response and execute actions.",
            metadata={"phase": phase, "missing_items": []},
        )
        yield emit_event(check_completed)
    else:
        detail = (
            f"Missing: {', '.join(missing[:4])}"
            if missing
            else "Contract requirements are not fully satisfied yet."
        )
        check_failed = activity_event_factory(
            event_type="llm.delivery_check_failed",
            title="Task contract not yet satisfied",
            detail=detail,
            metadata={
                "phase": phase,
                "ready_for_final_response": ready_final,
                "ready_for_external_actions": ready_actions,
                "missing_items": missing[:8],
                "reason": str(check.get("reason") or "").strip()[:260],
            },
        )
        yield emit_event(check_failed)
    return check


def build_contract_remediation_steps(
    *,
    check: dict[str, Any],
    registry: Any,
    remediation_signatures: set[str],
    allow_execute: bool = False,
    limit: int = 3,
) -> list[PlannedStep]:
    rows = check.get("recommended_remediation")
    if not isinstance(rows, list):
        return []
    suggested_steps: list[PlannedStep] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tool_id = str(row.get("tool_id") or "").strip()
        if not tool_id or tool_id not in LLM_ALLOWED_TOOL_IDS:
            continue
        params_raw = row.get("params")
        params = dict(params_raw) if isinstance(params_raw, dict) else {}
        try:
            signature = f"{tool_id}:{json.dumps(params, sort_keys=True, ensure_ascii=True)}"
        except Exception:
            signature = f"{tool_id}:{str(params)}"
        if signature in remediation_signatures:
            continue
        tool_meta = registry.get(tool_id).metadata
        if not allow_execute and tool_meta.action_class == "execute":
            continue
        title = " ".join(str(row.get("title") or tool_id).split()).strip()[:120]
        remediation_signatures.add(signature)
        suggested_steps.append(
            PlannedStep(
                tool_id=tool_id,
                title=f"Contract remediation: {title or tool_id}",
                params=params,
            )
        )
        if len(suggested_steps) >= max(1, int(limit)):
            break
    return suggested_steps
