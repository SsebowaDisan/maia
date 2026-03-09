from __future__ import annotations

import re
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.planner import PlannedStep

from ..models import TaskPreparation

EVIDENCE_TOOL_IDS = {
    "browser.playwright.inspect",
    "web.dataset.adapter",
    "web.extract.structured",
    "marketing.web_research",
    "workspace.drive.search",
    "documents.highlight.extract",
    "data.dataset.analyze",
    "analytics.ga4.report",
    "analytics.ga4.full_report",
    "analytics.chart.generate",
    "business.ga4_kpi_sheet_report",
    "sheets.read",
    "workspace.sheets.append",
}
ANALYTICS_EVIDENCE_TOOL_IDS = {
    "analytics.ga4.report",
    "analytics.ga4.full_report",
    "analytics.chart.generate",
    "business.ga4_kpi_sheet_report",
}
ANALYTICS_FACT_TOKENS = {
    "ga4",
    "google",
    "analytics",
    "metric",
    "metrics",
    "kpi",
    "session",
    "sessions",
    "conversion",
    "conversions",
    "traffic",
    "channel",
    "channels",
    "users",
    "audience",
    "report",
}
GA_INTENT_RE = re.compile(
    r"\b(google\s+analytics|ga4|analytics\s+property|property\s*id|google\s+property)\b",
    flags=re.IGNORECASE,
)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


def _tokenize(text: str) -> set[str]:
    return {match.group(0).lower() for match in WORD_RE.finditer(str(text or ""))}


def _step_text(step: PlannedStep) -> str:
    params_rows = [f"{key}: {value}" for key, value in step.params.items()]
    return "\n".join(
        [
            step.title,
            step.why_this_step,
            "\n".join(params_rows),
            "\n".join(step.expected_evidence),
        ]
    ).strip()


def _is_analytics_context(
    *,
    request: ChatRequest,
    steps: list[PlannedStep],
) -> bool:
    if any(step.tool_id in ANALYTICS_EVIDENCE_TOOL_IDS for step in steps):
        return True
    message = " ".join(
        [
            str(request.message or ""),
            str(request.agent_goal or ""),
        ]
    ).strip()
    return bool(GA_INTENT_RE.search(message))


def _fact_covered_by_step(*, fact: str, step: PlannedStep) -> bool:
    fact_tokens = _tokenize(fact)
    if not fact_tokens:
        return False
    if step.tool_id in ANALYTICS_EVIDENCE_TOOL_IDS:
        if fact_tokens.intersection(ANALYTICS_FACT_TOKENS):
            return True
    step_tokens = _tokenize(_step_text(step))
    if not step_tokens:
        return False
    overlap = fact_tokens.intersection(step_tokens)
    return len(overlap) >= 2


def _coverage_map(*, contract_facts: list[str], steps: list[PlannedStep]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for fact in contract_facts:
        fact_text = " ".join(str(fact or "").split()).strip()
        if not fact_text:
            continue
        linked_steps: list[str] = []
        for step in steps:
            if step.tool_id not in EVIDENCE_TOOL_IDS:
                continue
            if _fact_covered_by_step(fact=fact_text, step=step):
                linked_steps.append(step.tool_id)
        mapping[fact_text] = list(dict.fromkeys(linked_steps))
    return mapping


def summarize_fact_coverage(*, contract_facts: list[str], steps: list[PlannedStep]) -> dict[str, Any]:
    mapping = _coverage_map(contract_facts=contract_facts, steps=steps)
    missing_facts = [fact for fact, linked_steps in mapping.items() if not linked_steps]
    return {
        "required_fact_count": len(mapping),
        "covered_fact_count": len(mapping) - len(missing_facts),
        "missing_facts": missing_facts[:6],
        "fact_step_map": mapping,
    }


def enforce_evidence_path(
    *,
    request: ChatRequest,
    task_prep: TaskPreparation,
    steps: list[PlannedStep],
    highlight_color: str,
) -> list[PlannedStep]:
    analytics_context = _is_analytics_context(request=request, steps=steps)
    has_evidence_path = any(step.tool_id in EVIDENCE_TOOL_IDS for step in steps)
    if task_prep.contract_facts and not has_evidence_path:
        if analytics_context:
            evidence_step = PlannedStep(
                tool_id="analytics.ga4.full_report",
                title="Collect evidence for required facts",
                params={},
                why_this_step="Required facts need analytics-grounded evidence before final delivery.",
                expected_evidence=tuple(task_prep.contract_facts[:4]),
            )
        elif task_prep.task_intelligence.target_url:
            evidence_step = PlannedStep(
                tool_id="browser.playwright.inspect",
                title="Collect evidence for required facts",
                params={
                    "url": task_prep.task_intelligence.target_url,
                    "highlight_color": highlight_color,
                },
                why_this_step="Required facts need direct evidence before final delivery.",
                expected_evidence=tuple(task_prep.contract_facts[:4]),
            )
        else:
            evidence_step = PlannedStep(
                tool_id="marketing.web_research",
                title="Collect evidence for required facts",
                params={"query": request.message},
                why_this_step="Required facts need sourced evidence before final delivery.",
                expected_evidence=tuple(task_prep.contract_facts[:4]),
            )
        steps.insert(0, evidence_step)
    coverage = summarize_fact_coverage(contract_facts=task_prep.contract_facts, steps=steps)
    missing_facts = [
        str(item).strip()
        for item in coverage.get("missing_facts", [])
        if str(item).strip()
    ]
    if missing_facts:
        if analytics_context:
            remedial_step = PlannedStep(
                tool_id="analytics.ga4.full_report",
                title="Collect missing evidence for uncovered required facts",
                params={},
                why_this_step="Plan critic found uncovered required facts and regenerated analytics evidence.",
                expected_evidence=tuple(missing_facts[:4]),
            )
        elif task_prep.task_intelligence.target_url:
            remedial_step = PlannedStep(
                tool_id="browser.playwright.inspect",
                title="Collect missing evidence for uncovered required facts",
                params={
                    "url": task_prep.task_intelligence.target_url,
                    "highlight_color": highlight_color,
                },
                why_this_step="Plan critic found uncovered required facts and regenerated an evidence step.",
                expected_evidence=tuple(missing_facts[:4]),
            )
        else:
            remediation_query = "; ".join(missing_facts[:3]) or request.message
            remedial_step = PlannedStep(
                tool_id="marketing.web_research",
                title="Collect missing evidence for uncovered required facts",
                params={"query": remediation_query},
                why_this_step="Plan critic found uncovered required facts and regenerated an evidence step.",
                expected_evidence=tuple(missing_facts[:4]),
            )
        insert_at = len(steps)
        for idx, planned in enumerate(steps):
            if planned.tool_id in (
                "report.generate",
                "docs.create",
                "workspace.docs.research_notes",
            ):
                insert_at = idx
                break
        steps.insert(insert_at, remedial_step)
    return steps
