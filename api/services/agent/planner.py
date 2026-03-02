from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.services.agent.google_api_catalog import GOOGLE_API_TOOL_IDS
from api.schemas import ChatRequest
from api.services.agent.llm_intent import detect_web_routing_mode, enrich_task_intelligence
from api.services.agent.llm_planner import plan_with_llm
from api.services.agent.llm_plan_optimizer import optimize_plan_rows, rewrite_search_query
from api.services.agent.llm_runtime import env_bool
from api.services.agent.planner_helpers import intent_signals, sanitize_search_query
LLM_ALLOWED_TOOL_IDS = {
    "ads.google.performance",
    "analytics.chart.generate",
    "analytics.ga4.report",
    "business.cloud_incident_digest_email",
    "business.ga4_kpi_sheet_report",
    "business.invoice_workflow",
    "business.meeting_scheduler",
    "business.proposal_workflow",
    "business.route_plan",
    "browser.contact_form.send",
    "browser.playwright.inspect",
    "web.dataset.adapter",
    "web.extract.structured",
    "calendar.create_event",
    "data.dataset.analyze",
    "data.science.deep_learning.train",
    "data.science.ml.train",
    "data.science.profile",
    "data.science.visualize",
    "documents.highlight.extract",
    "docs.create",
    "email.draft",
    "email.send",
    "email.validate",
    "gmail.draft",
    "gmail.search",
    "gmail.send",
    "invoice.create",
    "invoice.send",
    "maps.distance_matrix",
    "maps.geocode",
    "marketing.competitor_profile",
    "marketing.local_discovery",
    "marketing.web_research",
    "report.generate",
    "slack.post_message",
    "workspace.docs.fill_template",
    "workspace.docs.research_notes",
    "workspace.drive.search",
    "workspace.sheets.append",
    "workspace.sheets.track_step",
}.union(GOOGLE_API_TOOL_IDS)

_CORE_FLOW_TOOL_IDS = {
    "browser.playwright.inspect",
    "web.dataset.adapter",
    "web.extract.structured",
    "documents.highlight.extract",
    "docs.create",
    "marketing.web_research",
    "report.generate",
    "workspace.docs.research_notes",
    "workspace.sheets.track_step",
}

DEFAULT_WEB_RESEARCH_PROVIDER = "brave_search"
DEFAULT_WEB_PROVIDER = "playwright_browser"


@dataclass(frozen=True)
class PlannedStep:
    tool_id: str
    title: str
    params: dict[str, Any]
    why_this_step: str = ""
    expected_evidence: tuple[str, ...] = ()


def resolve_web_routing(request: ChatRequest) -> dict[str, Any]:
    signals = intent_signals(request)
    routing = detect_web_routing_mode(
        message=request.message,
        agent_goal=request.agent_goal,
        heuristic=signals,
    )
    return routing if isinstance(routing, dict) else {}


def is_deep_research_request(request: ChatRequest) -> bool:
    return request.agent_mode == "company_agent" and bool(str(request.agent_goal or "").strip())


def _sort_steps(steps: list[PlannedStep], *, preferred_tool_ids: set[str] | None = None) -> list[PlannedStep]:
    priorities = {
        "browser.playwright.inspect": 5,
        "web.dataset.adapter": 6,
        "web.extract.structured": 7,
        "documents.highlight.extract": 8,
        "workspace.docs.research_notes": 10,
        "workspace.sheets.track_step": 15,
        "business.route_plan": 24,
        "marketing.web_research": 30,
        "marketing.local_discovery": 35,
        "marketing.competitor_profile": 40,
        "business.ga4_kpi_sheet_report": 42,
        "business.invoice_workflow": 43,
        "business.meeting_scheduler": 44,
        "business.proposal_workflow": 46,
        "data.dataset.analyze": 45,
        "data.science.profile": 45,
        "data.science.visualize": 46,
        "data.science.ml.train": 47,
        "data.science.deep_learning.train": 48,
        "report.generate": 70,
        "docs.create": 72,
        "workspace.docs.fill_template": 74,
        "gmail.draft": 82,
        "email.draft": 82,
        "business.cloud_incident_digest_email": 84,
        "browser.contact_form.send": 86,
        "gmail.send": 88,
        "email.send": 88,
    }
    decorated = []
    preferred = {str(item).strip() for item in (preferred_tool_ids or set()) if str(item).strip()}
    for idx, step in enumerate(steps):
        preferred_bias = -20 if step.tool_id in preferred else 0
        decorated.append((priorities.get(step.tool_id, 60) + preferred_bias, idx, step))
    decorated.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in decorated]


def _normalize_steps(
    request: ChatRequest,
    steps: list[PlannedStep],
    *,
    preferred_tool_ids: set[str] | None = None,
    web_routing: dict[str, Any] | None = None,
) -> list[PlannedStep]:
    signals = intent_signals(request)
    url = str(signals.get("url") or "")
    recipient = str(signals.get("recipient_email") or "")
    highlight_color = str(signals.get("highlight_color") or "yellow")
    routing = web_routing if isinstance(web_routing, dict) else detect_web_routing_mode(
        message=request.message,
        agent_goal=request.agent_goal,
        heuristic=signals,
    )
    routing_mode = str(routing.get("routing_mode") or "").strip().lower()
    scrape_url_requested = routing_mode == "url_scrape"
    online_research_requested = routing_mode == "online_research"
    company_agent_mode = request.agent_mode == "company_agent"
    has_highlight_extract = any(step.tool_id == "documents.highlight.extract" for step in steps)

    normalized: list[PlannedStep] = []
    for step in steps:
        params = dict(step.params)
        if step.tool_id == "browser.playwright.inspect":
            if url:
                params.setdefault("url", url)
            params.setdefault("web_provider", DEFAULT_WEB_PROVIDER)
            params.setdefault("highlight_color", highlight_color)
        if step.tool_id == "documents.highlight.extract":
            params.setdefault("highlight_color", highlight_color)
        if step.tool_id == "web.extract.structured":
            if url:
                params.setdefault("url", url)
            params.setdefault("extraction_goal", request.message)
        if step.tool_id == "web.dataset.adapter":
            if url:
                params.setdefault("url", url)
            params.setdefault("goal", request.message)
        if step.tool_id == "marketing.web_research":
            query = sanitize_search_query(
                str(params.get("query") or request.message),
                fallback_url=url,
            )
            params["query"] = rewrite_search_query(
                query=query,
                request=request,
                fallback_url=url,
            )
            params.setdefault("provider", DEFAULT_WEB_RESEARCH_PROVIDER)
            params.setdefault("allow_provider_fallback", False)
        if step.tool_id == "report.generate":
            params.setdefault("title", "Website Analysis Report")
            params.setdefault("summary", request.message)
        if step.tool_id in ("gmail.draft", "gmail.send", "email.draft", "email.send") and recipient:
            params.setdefault("to", recipient)
        if step.tool_id == "business.cloud_incident_digest_email" and recipient:
            params.setdefault("to", recipient)
            params.setdefault("send", True)
        if step.tool_id == "business.invoice_workflow" and recipient:
            params.setdefault("to", recipient)
        if step.tool_id == "business.meeting_scheduler" and recipient:
            params.setdefault("attendees", [recipient])
        if step.tool_id == "business.proposal_workflow" and recipient:
            params.setdefault("to", recipient)
        if step.tool_id == "business.route_plan":
            params.setdefault("mode", "driving")
        if step.tool_id == "business.ga4_kpi_sheet_report":
            params.setdefault("sheet_range", "Tracker!A1")
        if step.tool_id == "browser.contact_form.send":
            if url:
                params.setdefault("url", url)
            params.setdefault("subject", "Business inquiry")
            params.setdefault("message", request.message)
        if step.tool_id == "docs.create" and has_highlight_extract:
            params.setdefault("include_copied_highlights", True)
        normalized.append(
            PlannedStep(
                tool_id=step.tool_id,
                title=step.title,
                params=params,
                why_this_step=step.why_this_step,
                expected_evidence=step.expected_evidence,
            )
        )

    if scrape_url_requested and url:
        normalized = [step for step in normalized if step.tool_id != "marketing.web_research"]
        has_browser = any(step.tool_id == "browser.playwright.inspect" for step in normalized)
        if not has_browser:
            normalized.insert(
                0,
                PlannedStep(
                    tool_id="browser.playwright.inspect",
                    title="Inspect provided website in live browser",
                    params={
                        "url": url,
                        "web_provider": DEFAULT_WEB_PROVIDER,
                        "highlight_color": highlight_color,
                    },
                ),
            )
    elif online_research_requested and not url:
        has_web_research = any(step.tool_id == "marketing.web_research" for step in normalized)
        if not has_web_research:
            normalized.insert(
                0,
                PlannedStep(
                    tool_id="marketing.web_research",
                    title="Search online sources",
                    params={
                        "query": sanitize_search_query(request.message, fallback_url=""),
                        "provider": DEFAULT_WEB_RESEARCH_PROVIDER,
                        "allow_provider_fallback": False,
                    },
                ),
            )

    if company_agent_mode:
        normalized = [
            step
            for step in normalized
            if step.tool_id not in ("gmail.draft", "gmail.send", "email.draft", "email.send")
        ]

    deduped: list[PlannedStep] = []
    seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for step in normalized:
        signature = (
            step.tool_id,
            tuple(sorted((str(key), str(value)) for key, value in step.params.items())),
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(step)

    return _sort_steps(deduped, preferred_tool_ids=preferred_tool_ids)


def _augment_for_deep_research(
    request: ChatRequest,
    steps: list[PlannedStep],
    *,
    preferred_tool_ids: set[str] | None = None,
    web_routing: dict[str, Any] | None = None,
) -> list[PlannedStep]:
    routing = web_routing if isinstance(web_routing, dict) else resolve_web_routing(request)
    if not is_deep_research_request(request):
        return _normalize_steps(
            request,
            steps,
            preferred_tool_ids=preferred_tool_ids,
            web_routing=routing,
        )

    enriched = list(steps)
    intent = intent_signals(request)
    direct_url = str(intent.get("url") or "")

    has_web = any(step.tool_id == "marketing.web_research" for step in enriched)
    if not has_web and not direct_url:
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

    if direct_url:
        enriched = [step for step in enriched if step.tool_id != "browser.playwright.inspect"]
        enriched.insert(
            0,
            PlannedStep(
                tool_id="browser.playwright.inspect",
                title="Inspect provided website in live browser",
                params={"url": direct_url, "web_provider": DEFAULT_WEB_PROVIDER},
            ),
        )

    return _normalize_steps(
        request,
        enriched,
        preferred_tool_ids=preferred_tool_ids,
        web_routing=routing,
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

    if requires_delivery and not company_agent_mode:
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
    if env_bool("MAIA_AGENT_LLM_WIDE_TOOLSET_ENABLED", default=True):
        # LLM-first planning: allow the model to choose the best APIs/tools from full catalog.
        return set(LLM_ALLOWED_TOOL_IDS)
    if not preferred_tool_ids:
        return set(LLM_ALLOWED_TOOL_IDS)
    preferred = {
        str(item).strip()
        for item in preferred_tool_ids
        if str(item).strip() in LLM_ALLOWED_TOOL_IDS
    }
    if not preferred:
        return set(LLM_ALLOWED_TOOL_IDS)
    constrained = set(preferred).union(_CORE_FLOW_TOOL_IDS)
    # Keep all execution in the current company-agent flow even when scoping the tool set.
    constrained = {
        tool_id
        for tool_id in constrained
        if tool_id in LLM_ALLOWED_TOOL_IDS
    }
    return constrained or set(LLM_ALLOWED_TOOL_IDS)


def build_plan(
    request: ChatRequest,
    *,
    preferred_tool_ids: set[str] | None = None,
    web_routing: dict[str, Any] | None = None,
) -> list[PlannedStep]:
    steps: list[PlannedStep] = []
    routing = web_routing if isinstance(web_routing, dict) else resolve_web_routing(request)
    company_agent_mode = request.agent_mode == "company_agent"
    planning_allowed_tool_ids = _planning_allowed_tool_ids(
        preferred_tool_ids=preferred_tool_ids,
    )
    llm_rows = (
        plan_with_llm(
            request=request,
            allowed_tool_ids=planning_allowed_tool_ids,
            preferred_tool_ids=preferred_tool_ids,
        )
        if preferred_tool_ids is not None
        else plan_with_llm(
            request=request,
            allowed_tool_ids=planning_allowed_tool_ids,
        )
    )
    if llm_rows:
        llm_rows = optimize_plan_rows(
            request=request,
            rows=llm_rows,
            allowed_tool_ids=planning_allowed_tool_ids,
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
                web_routing=routing,
            )

    semantic_fallback_steps = _build_semantic_fallback_steps(request)
    if semantic_fallback_steps:
        return _augment_for_deep_research(
            request,
            semantic_fallback_steps,
            preferred_tool_ids=preferred_tool_ids,
            web_routing=routing,
        )

    signals = intent_signals(request)
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
    if recipient and not company_agent_mode:
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
        allowed_tool_ids=planning_allowed_tool_ids,
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
        web_routing=routing,
    )


def build_browser_followup_steps(
    web_result_data: dict[str, Any] | None,
    *,
    max_urls: int = 3,
) -> list[PlannedStep]:
    rows = []
    if isinstance(web_result_data, dict):
        raw_rows = web_result_data.get("items")
        if isinstance(raw_rows, list):
            rows = raw_rows

    followups: list[PlannedStep] = []
    seen_urls: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        label = str(row.get("label") or row.get("title") or url).strip()
        if not url or not url.startswith(("http://", "https://")) or url in seen_urls:
            continue
        seen_urls.add(url)
        followups.append(
            PlannedStep(
                tool_id="browser.playwright.inspect",
                title=f"Inspect source: {label[:72] or 'Website'}",
                params={"url": url},
            )
        )
        if len(followups) >= max(1, int(max_urls)):
            break

    return followups
