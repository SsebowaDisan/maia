from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger(__name__)

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
GA_PROBE_ALLOWED_TOOL_IDS = {
    "analytics.ga4.report",
    "analytics.ga4.full_report",
    "business.ga4_kpi_sheet_report",
    "analytics.chart.generate",
}
SYNTHESIS_TOOL_IDS = {
    "report.generate",
    "docs.create",
    "workspace.docs.research_notes",
    "workspace.docs.fill_template",
}
DELIVERY_TOOL_IDS = {
    "gmail.draft",
    "gmail.send",
    "email.draft",
    "email.send",
    "mailer.report_send",
}
EVIDENCE_TOOL_IDS = {
    "marketing.web_research",
    "web.extract.structured",
    "web.dataset.adapter",
    "browser.playwright.inspect",
    "documents.highlight.extract",
    "analytics.ga4.report",
    "analytics.ga4.full_report",
    "business.ga4_kpi_sheet_report",
}


def _is_allowed_url_scoped_probe(tool_id: str) -> bool:
    return str(tool_id or "").strip() in URL_SCOPED_PROBE_TOOL_IDS


def _request_has_explicit_file_scope(request: ChatRequest) -> bool:
    try:
        for selection in request.index_selection.values():
            file_ids = getattr(selection, "file_ids", []) or []
            if any(str(file_id).strip() for file_id in file_ids):
                return True
    except Exception:
        pass
    try:
        for attachment in request.attachments:
            if str(getattr(attachment, "file_id", "") or "").strip():
                return True
    except Exception:
        pass
    return False


def _is_google_analytics_probe_context(
    *,
    request: ChatRequest,
    task_prep: TaskPreparation,
    steps: list[PlannedStep],
) -> bool:
    del request
    if bool(getattr(task_prep.task_intelligence, "is_analytics_request", False)):
        return True
    if any(step.tool_id in GA_PROBE_ALLOWED_TOOL_IDS for step in steps):
        return True
    return False


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
    full_planning_message = "\n".join(
        [item for item in planning_message_lines if item]
    ).strip()
    if len(full_planning_message) > 1600:
        _log.warning(
            "build_planning_request: planning message truncated from %d to 1600 chars",
            len(full_planning_message),
        )
    planning_message = full_planning_message[:1600]
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
    analytics_context = _is_google_analytics_probe_context(
        request=request,
        task_prep=task_prep,
        steps=steps,
    )
    effective_allowed_tool_ids = (
        [
            tool_id
            for tool_id in allowed_tool_ids
            if tool_id in GA_PROBE_ALLOWED_TOOL_IDS
        ]
        if analytics_context
        else allowed_tool_ids
    )
    if analytics_context and not effective_allowed_tool_ids:
        return steps

    target_url = " ".join(str(task_prep.task_intelligence.target_url or "").split()).strip()
    explicit_file_scope = _request_has_explicit_file_scope(request)
    probe_rows = propose_fact_probe_steps(
        contract=task_prep.task_contract,
        request_message=request.message,
        target_url=target_url,
        existing_steps=[
            {"tool_id": item.tool_id, "title": item.title, "params": item.params}
            for item in steps[:20]
        ],
        allowed_tool_ids=effective_allowed_tool_ids,
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
        if tool_id == "documents.highlight.extract" and not explicit_file_scope:
            continue
        # When analytics context is active, GA tools are handled by the next filter;
        # skip the URL-scope restriction so analytics tools are not pre-filtered out.
        if target_url and not analytics_context and not _is_allowed_url_scoped_probe(tool_id):
            continue
        if analytics_context and tool_id not in GA_PROBE_ALLOWED_TOOL_IDS:
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


def enforce_contract_synthesis_step(
    *,
    request: ChatRequest,
    task_prep: TaskPreparation,
    steps: list[PlannedStep],
    allowed_tool_ids: set[str] | None = None,
) -> list[PlannedStep]:
    allowed = {str(tool_id).strip() for tool_id in (allowed_tool_ids or set()) if str(tool_id).strip()}
    if allowed and "report.generate" not in allowed:
        return steps
    contract_outputs = [
        " ".join(str(item).split()).strip()
        for item in task_prep.contract_outputs
        if " ".join(str(item).split()).strip()
    ]
    task_contract_outputs = task_prep.task_contract.get("required_outputs")
    if isinstance(task_contract_outputs, list):
        contract_outputs.extend(
            [
                " ".join(str(item).split()).strip()
                for item in task_contract_outputs
                if " ".join(str(item).split()).strip()
            ]
        )
    contract_outputs.extend(
        [
            " ".join(str(item).split()).strip()
            for item in task_prep.planned_deliverables
            if " ".join(str(item).split()).strip()
        ]
    )
    contract_outputs = list(dict.fromkeys(contract_outputs))

    if any(step.tool_id in SYNTHESIS_TOOL_IDS for step in steps):
        return steps
    if not any(step.tool_id in EVIDENCE_TOOL_IDS for step in steps):
        return steps

    summary = (
        task_prep.contract_objective
        or task_prep.rewritten_task
        or request.message
    )
    required_facts = [
        " ".join(str(item).split()).strip()
        for item in task_prep.contract_facts
        if " ".join(str(item).split()).strip()
    ]
    required_outputs = contract_outputs[:3]
    summary_parts = [summary]
    if required_facts:
        summary_parts.append("Must explicitly cover: " + "; ".join(required_facts[:4]))
    if required_outputs:
        summary_parts.append("Deliverable expectations: " + "; ".join(required_outputs))
    summary = " ".join(part for part in summary_parts if part).strip()
    synthesis_step = PlannedStep(
        tool_id="report.generate",
        title="Synthesize cited research brief",
        params={
            "title": "Research Brief",
            "summary": summary,
        },
        why_this_step="Convert gathered evidence into a structured, source-backed brief before verification or delivery.",
        expected_evidence=tuple(contract_outputs[:4]),
    )
    insert_at = len(steps)
    for idx, step in enumerate(steps):
        if step.tool_id in DELIVERY_TOOL_IDS:
            insert_at = idx
            break
    steps.insert(insert_at, synthesis_step)
    return steps
