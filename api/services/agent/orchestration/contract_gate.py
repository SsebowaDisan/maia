from __future__ import annotations

import json
from collections.abc import Callable, Generator
from typing import Any
from urllib.parse import urlparse

from api.services.agent.llm_contracts import verify_task_contract_fulfillment
from api.services.agent.models import AgentAction, AgentActivityEvent, AgentSource
from api.services.agent.planner import LLM_ALLOWED_TOOL_IDS, PlannedStep
from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.contract_verification_support import (
    extract_source_evidence_lines,
    infer_source_origin_label,
    infer_source_scope_summary,
)

from .side_effect_status import EXTERNAL_ACTION_KEYS, side_effect_status_from_actions


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
        metadata = source.metadata if isinstance(source.metadata, dict) else {}
        origin = infer_source_origin_label(
            label=str(source.label or "").strip(),
            url=str(source.url or "").strip(),
            metadata=metadata,
        )
        scope = infer_source_scope_summary(
            label=str(source.label or "").strip(),
            url=str(source.url or "").strip(),
            metadata=metadata,
        )
        rows.append(
            {
                "label": str(source.label or "").strip(),
                "url": str(source.url or "").strip(),
                "score": source.score,
                "origin": origin,
                "scope_topic": scope,
                "evidence_lines": extract_source_evidence_lines(metadata)[:3],
                "metadata": metadata,
            }
        )
    return rows


def _host_from_url(url: str) -> str:
    try:
        host = str(urlparse(str(url or "").strip()).hostname or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _filter_sources_for_contract_scope(
    *,
    sources: list[AgentSource],
    target_url: str,
) -> list[AgentSource]:
    target_host = _host_from_url(target_url)
    if not target_host:
        return sources
    scoped = [
        source
        for source in sources
        if not str(source.url or "").strip()
        or (
            _host_from_url(str(source.url or "").strip()) == target_host
            or _host_from_url(str(source.url or "").strip()).endswith(f".{target_host}")
        )
    ]
    return scoped if scoped else sources


def _required_action_keys(task_contract: dict[str, Any]) -> set[str]:
    rows = task_contract.get("required_actions")
    if not isinstance(rows, list):
        return set()
    return {
        " ".join(str(item or "").split()).strip().lower()
        for item in rows
        if " ".join(str(item or "").split()).strip()
    }


def _normalized_side_effect_status(value: str) -> str:
    cleaned = " ".join(str(value or "").split()).strip().lower()
    if cleaned in {"success", "completed", "sent"}:
        return "completed"
    if cleaned in {"pending", "in_progress", "started"}:
        return "pending"
    if cleaned in {"failed", "blocked", "skipped"}:
        return cleaned
    return cleaned or "unknown"


def _enforce_side_effect_authority(
    *,
    check: dict[str, Any],
    task_contract: dict[str, Any],
    side_effect_status: dict[str, dict[str, Any]],
    pending_action_tool_id: str,
) -> dict[str, Any]:
    required_action_keys = _required_action_keys(task_contract)
    if not required_action_keys:
        check["side_effect_status"] = side_effect_status
        return check

    missing_items = [
        str(item).strip()
        for item in check.get("missing_items", [])
        if str(item).strip()
    ]
    reason = " ".join(str(check.get("reason") or "").split()).strip()
    remediation_rows = [
        dict(row)
        for row in check.get("recommended_remediation", [])
        if isinstance(row, dict)
    ]
    pending_tool_id = " ".join(str(pending_action_tool_id or "").split()).strip()
    for action_key in EXTERNAL_ACTION_KEYS:
        if action_key not in required_action_keys:
            continue
        status_row = side_effect_status.get(action_key)
        status_value = _normalized_side_effect_status(
            str(status_row.get("status") or "") if isinstance(status_row, dict) else ""
        )
        if status_value == "completed":
            missing_items = [
                item
                for item in missing_items
                if f"required action not completed: {action_key}" not in item.lower()
                and f"external action failed: {action_key}" not in item.lower()
            ]
            continue
        if pending_tool_id and status_value == "pending":
            continue
        if status_value in {"failed", "blocked", "skipped"}:
            authoritative_missing = f"External action failed: {action_key} ({status_value})"
            if authoritative_missing not in missing_items:
                missing_items.append(authoritative_missing)
            if action_key == "send_email" and not any(
                str(row.get("tool_id") or "").strip() in {"gmail.draft", "email.draft", "mailer.report_send"}
                for row in remediation_rows
            ):
                remediation_rows.append(
                    {
                        "tool_id": "gmail.draft",
                        "title": "Prepare delivery retry draft after failure",
                        "params": {},
                    }
                )
            if not reason:
                reason = f"Required external action '{action_key}' ended with status {status_value}."

    check["missing_items"] = missing_items[:8]
    check["reason"] = reason[:320]
    check["recommended_remediation"] = remediation_rows[:4]
    if check["missing_items"]:
        check["ready_for_external_actions"] = False
        check["ready_for_final_response"] = False
    check["side_effect_status"] = side_effect_status
    return check


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
    target_url = " ".join(str(execution_context.settings.get("__task_target_url") or "").split()).strip()
    scoped_sources = _filter_sources_for_contract_scope(
        sources=sources,
        target_url=target_url,
    )
    runtime_side_effect_status = execution_context.settings.get("__side_effect_status")
    side_effect_status = (
        dict(runtime_side_effect_status)
        if isinstance(runtime_side_effect_status, dict)
        else {}
    )
    action_side_effects = side_effect_status_from_actions(actions=actions)
    for key, row in action_side_effects.items():
        if key not in side_effect_status:
            side_effect_status[key] = row
    execution_context.settings["__side_effect_status"] = side_effect_status
    scoped_allowed_tool_ids = execution_context.settings.get("__allowed_tool_ids")
    allowed_tool_ids = (
        [
            str(item).strip()
            for item in scoped_allowed_tool_ids
            if str(item).strip()
        ]
        if isinstance(scoped_allowed_tool_ids, list)
        else sorted(list(LLM_ALLOWED_TOOL_IDS))
    )
    check = verify_task_contract_fulfillment(
        contract=task_contract,
        request_message=request_message,
        executed_steps=executed_steps,
        actions=action_rows_for_contract_check(actions),
        report_body=report_body,
        sources=source_rows_for_contract_check(scoped_sources),
        allowed_tool_ids=allowed_tool_ids,
        pending_action_tool_id=pending_action_tool_id,
        side_effect_status=side_effect_status,
    )
    check = _enforce_side_effect_authority(
        check=check,
        task_contract=task_contract,
        side_effect_status=side_effect_status,
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
            metadata={
                "phase": phase,
                "missing_items": [],
                "side_effect_status": side_effect_status,
            },
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
                "side_effect_status": side_effect_status,
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
