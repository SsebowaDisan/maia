from __future__ import annotations

import json
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.llm_contracts import propose_fact_probe_steps
from api.services.agent.planner import LLM_ALLOWED_TOOL_IDS, PlannedStep

from ..models import TaskPreparation

URL_SCOPED_PROBE_TOOL_IDS = {
    "browser.playwright.inspect",
    "marketing.web_research",
    "web.extract.structured",
    "web.dataset.adapter",
    "documents.highlight.extract",
}


def _is_allowed_url_scoped_probe(tool_id: str) -> bool:
    return str(tool_id or "").strip() in URL_SCOPED_PROBE_TOOL_IDS


def build_planning_request(
    *,
    request: ChatRequest,
    task_prep: TaskPreparation,
) -> tuple[ChatRequest, str]:
    planning_request = request
    planning_message_lines = [task_prep.rewritten_task or request.message.strip()]
    if task_prep.contract_objective:
        planning_message_lines.append("Contract objective: " + task_prep.contract_objective)
    if task_prep.contract_outputs:
        planning_message_lines.append(
            "Required outputs: " + "; ".join(task_prep.contract_outputs[:6])
        )
    if task_prep.contract_facts:
        planning_message_lines.append(
            "Required facts: " + "; ".join(task_prep.contract_facts[:6])
        )
    if task_prep.contract_success_checks:
        planning_message_lines.append(
            "Success checks: " + "; ".join(task_prep.contract_success_checks[:6])
        )
    if task_prep.planned_deliverables:
        planning_message_lines.append(
            "Deliverables: " + "; ".join(task_prep.planned_deliverables[:6])
        )
    if task_prep.planned_constraints:
        planning_message_lines.append(
            "Constraints: " + "; ".join(task_prep.planned_constraints[:6])
        )
    if task_prep.conversation_summary:
        planning_message_lines.append(
            f"Conversation context: {task_prep.conversation_summary}"
        )
    planning_message = "\n".join(
        [item for item in planning_message_lines if item]
    ).strip()[:1600]
    if planning_message:
        try:
            planning_request = request.model_copy(update={"message": planning_message})
        except Exception:
            planning_request = request
    return planning_request, planning_message


def collect_probe_allowed_tool_ids(registry: Any) -> list[str]:
    probe_allowed_tool_ids: list[str] = []
    for tool_id in sorted(list(LLM_ALLOWED_TOOL_IDS)):
        try:
            tool_meta = registry.get(tool_id).metadata
        except Exception:
            continue
        if tool_meta.action_class in {"read", "draft"}:
            probe_allowed_tool_ids.append(tool_id)
    return probe_allowed_tool_ids


def insert_contract_probe_steps(
    *,
    request: ChatRequest,
    task_prep: TaskPreparation,
    steps: list[PlannedStep],
    allowed_tool_ids: list[str],
) -> list[PlannedStep]:
    target_url = " ".join(str(task_prep.task_intelligence.target_url or "").split()).strip()
    probe_rows = propose_fact_probe_steps(
        contract=task_prep.task_contract,
        request_message=request.message,
        target_url=target_url,
        existing_steps=[
            {"tool_id": item.tool_id, "title": item.title, "params": item.params}
            for item in steps[:20]
        ],
        allowed_tool_ids=allowed_tool_ids,
        max_steps=4,
    )
    existing_plan_signatures: set[str] = set()
    for item in steps:
        try:
            signature = (
                f"{item.tool_id}:{json.dumps(item.params, ensure_ascii=True, sort_keys=True)}"
            )
        except Exception:
            signature = f"{item.tool_id}:{str(item.params)}"
        existing_plan_signatures.add(signature)

    probe_steps: list[PlannedStep] = []
    for row in probe_rows:
        tool_id = str(row.get("tool_id") or "").strip()
        if not tool_id:
            continue
        if target_url and not _is_allowed_url_scoped_probe(tool_id):
            continue
        params_raw = row.get("params")
        params_dict = dict(params_raw) if isinstance(params_raw, dict) else {}
        try:
            signature = (
                f"{tool_id}:{json.dumps(params_dict, ensure_ascii=True, sort_keys=True)}"
            )
        except Exception:
            signature = f"{tool_id}:{str(params_dict)}"
        if signature in existing_plan_signatures:
            continue
        existing_plan_signatures.add(signature)
        probe_steps.append(
            PlannedStep(
                tool_id=tool_id,
                title=str(row.get("title") or f"Fact probe: {tool_id}"),
                params=params_dict,
            )
        )
        if len(probe_steps) >= 4:
            break

    if probe_steps:
        insert_at = len(steps)
        for idx, planned in enumerate(steps):
            if planned.tool_id in (
                "report.generate",
                "docs.create",
                "workspace.docs.research_notes",
            ):
                insert_at = idx
                break
        steps[insert_at:insert_at] = probe_steps

    return steps
