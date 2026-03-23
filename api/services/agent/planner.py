from __future__ import annotations

from typing import Any

from api.schemas import ChatRequest
from api.services.agent.llm_intent import detect_web_routing_mode, enrich_task_intelligence
from api.services.agent.llm_planner import plan_with_llm
from api.services.agent.llm_plan_optimizer import optimize_plan_rows
from api.services.agent.planner_helpers import intent_signals
from api.services.agent.research_depth_profile import derive_research_depth_profile

from .planner_config import (
    DEFAULT_WEB_PROVIDER,
    DEFAULT_WEB_RESEARCH_PROVIDER,
    LLM_ALLOWED_TOOL_IDS,
    planning_allowed_tool_ids,
)
from .planner_followups import build_browser_followup_steps
from .planner_models import PlannedStep
from .planner_normalization import normalize_steps

GA_TOOL_IDS = {
    "analytics.ga4.report",
    "analytics.ga4.full_report",
    "business.ga4_kpi_sheet_report",
}

GA_WEB_TOOL_IDS = {
    "marketing.web_research",
    "browser.playwright.inspect",
    "web.extract.structured",
    "web.dataset.adapter",
}

GA_DELIVERY_TOOL_IDS = {
    "gmail.draft",
    "gmail.send",
}

PLANNING_CONTEXT_PREFIXES = (
    "contract objective:",
    "required outputs:",
    "required facts:",
    "success checks:",
    "deliverables:",
    "constraints:",
    "conversation context:",
)


def resolve_web_routing(request: ChatRequest) -> dict[str, Any]:
    signals = intent_signals(request)
    routing = detect_web_routing_mode(
        message=request.message,
        agent_goal=request.agent_goal,
        heuristic=signals,
    )
    return routing if isinstance(routing, dict) else {}


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _has_deep_research_override(request: ChatRequest) -> bool:
    overrides = (
        dict(request.setting_overrides)
        if isinstance(request.setting_overrides, dict)
        else {}
    )
    if _truthy(overrides.get("__deep_search_enabled"), default=False):
        return True

    depth_tier = " ".join(str(overrides.get("__research_depth_tier") or "").split()).strip().lower()
    if depth_tier in {"deep_research", "deep_analytics"}:
        return True

    profile_raw = overrides.get("__research_depth_profile")
    profile = profile_raw if isinstance(profile_raw, dict) else {}
    profile_tier = " ".join(str(profile.get("tier") or "").split()).strip().lower()
    return profile_tier in {"deep_research", "deep_analytics"}


def is_deep_research_request(request: ChatRequest) -> bool:
    agent_mode = str(request.agent_mode or "").strip().lower()
    if agent_mode == "deep_search":
        return True
    if _has_deep_research_override(request):
        return True
    profile = derive_research_depth_profile(
        message=request.message,
        agent_goal=request.agent_goal,
        user_preferences={},
        agent_mode=request.agent_mode,
    )
    return profile.tier in {"deep_research", "deep_analytics"}


def _is_google_analytics_request(
    request: ChatRequest,
    *,
    intent: dict[str, Any] | None = None,
    preferred_tool_ids: set[str] | None = None,
) -> bool:
    intent_rows = intent if isinstance(intent, dict) else {}
    if bool(intent_rows.get("is_analytics_request")):
        return True
    intent_tags = intent_rows.get("intent_tags")
    if isinstance(intent_tags, list):
        lowered_tags = {
            " ".join(str(item).split()).strip().lower()
            for item in intent_tags
            if str(item).strip()
        }
        if any("analytics" in tag or "ga4" in tag for tag in lowered_tags):
            return True
    signal_text_parts = [
        str(request.message or ""),
        str(request.agent_goal or ""),
        str(intent_rows.get("objective") or ""),
        str(intent_rows.get("summary") or ""),
    ]
    signal_text = " ".join(signal_text_parts).lower()
    return any(
        marker in signal_text
        for marker in ("google analytics", "google-analytics", "ga4", "analytics property")
    )


def _ga_sheet_requested(
    request: ChatRequest,
    *,
    intent: dict[str, Any] | None = None,
    preferred_tool_ids: set[str] | None = None,
) -> bool:
    intent_rows = intent if isinstance(intent, dict) else {}
    if bool(intent_rows.get("wants_sheets_output")):
        return True
    signal_text_parts = [
        str(request.message or ""),
        str(request.agent_goal or ""),
        str(intent_rows.get("objective") or ""),
        str(intent_rows.get("summary") or ""),
    ]
    signal_text = " ".join(signal_text_parts).lower()
    return any(marker in signal_text for marker in ("google sheets", "spreadsheet", "sheet", "tracker"))


def _ensure_ga_plan_shape(
    request: ChatRequest,
    *,
    steps: list[PlannedStep],
    preferred_tool_ids: set[str] | None,
    intent: dict[str, Any] | None,
) -> list[PlannedStep]:
    if not _is_google_analytics_request(
        request,
        intent=intent,
        preferred_tool_ids=preferred_tool_ids,
    ):
        return steps

    ga_sheet_requested = _ga_sheet_requested(
        request,
        intent=intent,
        preferred_tool_ids=preferred_tool_ids,
    )
    cleaned: list[PlannedStep] = []
    for step in steps:
        if step.tool_id in GA_WEB_TOOL_IDS:
            continue
        if step.tool_id not in GA_TOOL_IDS and step.tool_id != "report.generate" and step.tool_id not in GA_DELIVERY_TOOL_IDS:
            continue
        if step.tool_id == "business.ga4_kpi_sheet_report" and not ga_sheet_requested:
            continue
        params = dict(step.params)
        if step.tool_id == "report.generate":
            params.setdefault("summary", request.message)
            # GA flows should not silently reuse stale web source snapshots.
            params.setdefault("sources", [])
        cleaned.append(
            PlannedStep(
                tool_id=step.tool_id,
                title=step.title,
                params=params,
                why_this_step=step.why_this_step,
                expected_evidence=step.expected_evidence,
            )
        )

    tool_ids = [step.tool_id for step in cleaned]
    if "analytics.ga4.full_report" not in tool_ids:
        cleaned.insert(
            0,
            PlannedStep(
                tool_id="analytics.ga4.full_report",
                title="Run full GA4 report",
                params={},
                why_this_step="Fetch core GA4 metrics and period comparisons before synthesis.",
                expected_evidence=(
                    "Sessions, users, conversions, and bounce rate trends",
                    "Channel, page, device, and geography breakdowns",
                ),
            ),
        )
        tool_ids.insert(0, "analytics.ga4.full_report")

    if ga_sheet_requested and "business.ga4_kpi_sheet_report" not in tool_ids:
        insert_at = 1 if cleaned and cleaned[0].tool_id == "analytics.ga4.full_report" else 0
        cleaned.insert(
            insert_at,
            PlannedStep(
                tool_id="business.ga4_kpi_sheet_report",
                title="Write GA4 KPI sheet update",
                params={"sheet_range": "Tracker!A1"},
                why_this_step="Persist GA4 KPI rows to the shared tracker for repeatable reporting.",
                expected_evidence=("Updated KPI rows in Google Sheets",),
            ),
        )
        tool_ids.insert(insert_at, "business.ga4_kpi_sheet_report")

    if "report.generate" not in tool_ids:
        cleaned.append(
            PlannedStep(
                tool_id="report.generate",
                title="Generate GA4 executive report",
                params={
                    "summary": request.message,
                    "sources": [],
                },
                why_this_step="Convert analytics outputs into an executive-ready narrative.",
                expected_evidence=(
                    "Executive summary with KPI deltas",
                    "Detailed analytics interpretation",
                ),
            )
        )

    return cleaned


def _augment_for_deep_research(
    request: ChatRequest,
    steps: list[PlannedStep],
    *,
    preferred_tool_ids: set[str] | None = None,
    intent: dict[str, Any] | None = None,
    web_routing: dict[str, Any] | None = None,
    deep_research_mode: bool | None = None,
) -> list[PlannedStep]:
    routing = web_routing if isinstance(web_routing, dict) else resolve_web_routing(request)
    if deep_research_mode is None:
        deep_research_mode = is_deep_research_request(request)
    company_agent_mode = request.agent_mode == "company_agent"
    effective_intent = intent if isinstance(intent, dict) else intent_signals(request)
    shaped_steps = _ensure_ga_plan_shape(
        request,
        steps=steps,
        preferred_tool_ids=preferred_tool_ids,
        intent=effective_intent,
    )
    if not deep_research_mode:
        return normalize_steps(
            request,
            shaped_steps,
            preferred_tool_ids=preferred_tool_ids,
            intent=effective_intent,
            web_routing=routing,
            deep_research_mode=False,
            company_agent_mode=company_agent_mode,
        )

    analytics_request = _is_google_analytics_request(
        request,
        intent=effective_intent,
        preferred_tool_ids=preferred_tool_ids,
    )
    enriched = list(shaped_steps)
    direct_url = str(effective_intent.get("url") or "")

    has_web = any(step.tool_id == "marketing.web_research" for step in enriched)
    if not has_web and not analytics_request:
        enriched.insert(
            0,
            PlannedStep(
                tool_id="marketing.web_research",
                title="Search online sources",
                params={
                    "query": request.message,
                    "provider": DEFAULT_WEB_RESEARCH_PROVIDER,
                    "allow_provider_fallback": False,
                },
            ),
        )

    has_report = any(step.tool_id == "report.generate" for step in enriched)
    if not has_report:
        enriched.append(
            PlannedStep(
                tool_id="report.generate",
                title="Generate deep research report",
                params={"summary": request.message},
            )
        )

    if direct_url and not analytics_request:
        enriched = [step for step in enriched if step.tool_id != "browser.playwright.inspect"]
        enriched.insert(
            0,
            PlannedStep(
                tool_id="browser.playwright.inspect",
                title="Inspect provided website in live browser",
                params={"url": direct_url, "web_provider": DEFAULT_WEB_PROVIDER},
            ),
        )

    return normalize_steps(
        request,
        enriched,
        preferred_tool_ids=preferred_tool_ids,
        intent=effective_intent,
        web_routing=routing,
        deep_research_mode=True,
        company_agent_mode=company_agent_mode,
    )


def _build_semantic_fallback_steps(request: ChatRequest) -> list[PlannedStep]:
    """LLM-intent fallback when the dedicated planner returns no rows."""
    heuristic = intent_signals(request)
    llm_intent = enrich_task_intelligence(
        message=request.message,
        agent_goal=request.agent_goal,
        heuristic=heuristic,
    )
    if not isinstance(llm_intent, dict) or not llm_intent:
        return []

    company_agent_mode = request.agent_mode == "company_agent"
    objective = str(llm_intent.get("objective") or request.message or "").strip()
    target_url = str(llm_intent.get("target_url") or heuristic.get("url") or "").strip()
    delivery_email = str(
        llm_intent.get("delivery_email") or heuristic.get("recipient_email") or ""
    ).strip()
    llm_tags = llm_intent.get("intent_tags")
    intent_tags = {
        str(item).strip().lower()
        for item in llm_tags
        if str(item).strip()
    } if isinstance(llm_tags, list) else set()

    requires_web = bool(llm_intent.get("requires_web_inspection")) or ("web_research" in intent_tags)
    if target_url:
        requires_web = True
    requires_contact_form_submission = bool(
        llm_intent.get("requires_contact_form_submission")
    )
    if "contact_form_submission" in intent_tags:
        requires_contact_form_submission = True
    requires_delivery = bool(llm_intent.get("requires_delivery")) and bool(delivery_email)
    requested_report = bool(llm_intent.get("requested_report")) or ("report_generation" in intent_tags) or company_agent_mode

    steps: list[PlannedStep] = []
    if target_url:
        steps.append(
            PlannedStep(
                tool_id="browser.playwright.inspect",
                title="Inspect provided website in live browser",
                params={"url": target_url, "web_provider": DEFAULT_WEB_PROVIDER},
            )
        )
    elif requires_web:
        steps.append(
            PlannedStep(
                tool_id="marketing.web_research",
                title="Search online sources",
                params={
                    "query": objective or request.message,
                    "provider": DEFAULT_WEB_RESEARCH_PROVIDER,
                    "allow_provider_fallback": False,
                },
            )
        )

    if requested_report:
        steps.append(
            PlannedStep(
                tool_id="report.generate",
                title="Generate report draft",
                params={"summary": objective or request.message},
            )
        )

    if "docs_write" in intent_tags:
        steps.append(
            PlannedStep(
                tool_id="docs.create",
                title="Create structured document draft",
                params={"title": "Company Draft", "body": objective or request.message},
            )
        )

    if target_url and requires_contact_form_submission:
        steps.append(
            PlannedStep(
                tool_id="browser.contact_form.send",
                title="Fill and submit website contact form",
                params={
                    "url": target_url,
                    "subject": "Business inquiry",
                    "message": objective or request.message,
                },
            )
        )

    if requires_delivery and not company_agent_mode and not is_deep_research_request(request):
        steps.append(
            PlannedStep(
                tool_id="gmail.draft",
                title="Create Gmail draft",
                params={"to": delivery_email},
            )
        )
        steps.append(
            PlannedStep(
                tool_id="gmail.send",
                title="Send Gmail message",
                params={"to": delivery_email},
            )
        )

    return steps


def _planning_allowed_tool_ids(
    *,
    preferred_tool_ids: set[str] | None,
) -> set[str]:
    return planning_allowed_tool_ids(preferred_tool_ids=preferred_tool_ids)


def build_plan(
    request: ChatRequest,
    *,
    preferred_tool_ids: set[str] | None = None,
    web_routing: dict[str, Any] | None = None,
    deep_research_mode: bool | None = None,
) -> list[PlannedStep]:
    steps: list[PlannedStep] = []
    routing = web_routing if isinstance(web_routing, dict) else resolve_web_routing(request)
    signals = intent_signals(request)
    llm_intent = enrich_task_intelligence(
        message=request.message,
        agent_goal=request.agent_goal,
        heuristic=signals,
    )
    if isinstance(llm_intent, dict):
        signals = {**signals, **llm_intent}
    company_agent_mode = request.agent_mode == "company_agent"
    planning_allowed_ids = _planning_allowed_tool_ids(
        preferred_tool_ids=preferred_tool_ids,
    )
    llm_rows = (
        plan_with_llm(
            request=request,
            allowed_tool_ids=planning_allowed_ids,
            preferred_tool_ids=preferred_tool_ids,
            intent_signals=signals,
        )
        if preferred_tool_ids is not None
        else plan_with_llm(
            request=request,
            allowed_tool_ids=planning_allowed_ids,
            intent_signals=signals,
        )
    )
    if llm_rows:
        llm_rows = optimize_plan_rows(
            request=request,
            rows=llm_rows,
            allowed_tool_ids=planning_allowed_ids,
        )
        llm_steps: list[PlannedStep] = []
        for row in llm_rows:
            if not isinstance(row, dict):
                continue
            tool_id = str(row.get("tool_id") or "").strip()
            if not tool_id:
                continue
            title = str(row.get("title") or "").strip() or tool_id
            params = row.get("params")
            llm_steps.append(
                PlannedStep(
                    tool_id=tool_id,
                    title=title,
                    params=dict(params) if isinstance(params, dict) else {},
                    why_this_step=" ".join(str(row.get("why_this_step") or "").split()).strip()[:240],
                    expected_evidence=tuple(
                        [
                            " ".join(str(item).split()).strip()[:220]
                            for item in (
                                row.get("expected_evidence")
                                if isinstance(row.get("expected_evidence"), list)
                                else []
                            )
                            if " ".join(str(item).split()).strip()
                        ][:4]
                    ),
                )
            )
        if llm_steps:
            return _augment_for_deep_research(
                request,
                llm_steps,
                preferred_tool_ids=preferred_tool_ids,
                intent=signals,
                web_routing=routing,
                deep_research_mode=deep_research_mode,
            )

    semantic_fallback_steps = _build_semantic_fallback_steps(request)
    if semantic_fallback_steps:
        return _augment_for_deep_research(
            request,
            semantic_fallback_steps,
            preferred_tool_ids=preferred_tool_ids,
            intent=signals,
            web_routing=routing,
            deep_research_mode=deep_research_mode,
        )

    target_url = str(signals.get("url") or "")
    recipient = str(signals.get("recipient_email") or "")
    if target_url:
        steps.append(
            PlannedStep(
                tool_id="browser.playwright.inspect",
                title="Inspect provided website in live browser",
                params={"url": target_url, "web_provider": DEFAULT_WEB_PROVIDER},
            )
        )
    else:
        steps.append(
            PlannedStep(
                tool_id="marketing.web_research",
                title="Search online sources",
                params={
                    "query": request.message,
                    "provider": DEFAULT_WEB_RESEARCH_PROVIDER,
                    "allow_provider_fallback": False,
                },
            )
        )
    steps.append(
        PlannedStep(
            tool_id="report.generate",
            title="Create concise executive output",
            params={"summary": request.message},
        )
    )
    effective_deep_research_mode = (
        deep_research_mode if deep_research_mode is not None else is_deep_research_request(request)
    )
    if recipient and not company_agent_mode and not effective_deep_research_mode:
        steps.append(
            PlannedStep(
                tool_id="gmail.draft",
                title="Create Gmail draft",
                params={"to": recipient},
            )
        )
        steps.append(
            PlannedStep(
                tool_id="gmail.send",
                title="Send Gmail message",
                params={"to": recipient},
            )
        )

    candidate_rows = [
        {
            "tool_id": step.tool_id,
            "title": step.title,
            "params": dict(step.params),
            "why_this_step": step.why_this_step,
            "expected_evidence": list(step.expected_evidence),
        }
        for step in steps
    ]
    optimized_rows = optimize_plan_rows(
        request=request,
        rows=candidate_rows,
        allowed_tool_ids=planning_allowed_ids,
    )
    if optimized_rows:
        steps = [
            PlannedStep(
                tool_id=str(row.get("tool_id") or "").strip(),
                title=str(row.get("title") or "").strip() or str(row.get("tool_id") or "Planned step"),
                params=dict(row.get("params")) if isinstance(row.get("params"), dict) else {},
                why_this_step=" ".join(str(row.get("why_this_step") or "").split()).strip()[:240],
                expected_evidence=tuple(
                    [
                        " ".join(str(item).split()).strip()[:220]
                        for item in (
                            row.get("expected_evidence")
                            if isinstance(row.get("expected_evidence"), list)
                            else []
                        )
                        if " ".join(str(item).split()).strip()
                    ][:4]
                ),
            )
            for row in optimized_rows
            if str(row.get("tool_id") or "").strip()
        ] or steps
    return _augment_for_deep_research(
        request,
        steps,
        preferred_tool_ids=preferred_tool_ids,
        intent=signals,
        web_routing=routing,
        deep_research_mode=deep_research_mode,
    )


__all__ = [
    "DEFAULT_WEB_PROVIDER",
    "DEFAULT_WEB_RESEARCH_PROVIDER",
    "LLM_ALLOWED_TOOL_IDS",
    "PlannedStep",
    "build_browser_followup_steps",
    "build_plan",
    "is_deep_research_request",
    "resolve_web_routing",
]
