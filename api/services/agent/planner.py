from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlparse

from api.schemas import ChatRequest
from api.services.agent.llm_intent import enrich_task_intelligence
from api.services.agent.llm_planner import plan_with_llm
from api.services.agent.llm_plan_optimizer import optimize_plan_rows, rewrite_search_query

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
LLM_ALLOWED_TOOL_IDS = {
    "ads.google.performance",
    "analytics.chart.generate",
    "analytics.ga4.report",
    "browser.playwright.inspect",
    "calendar.create_event",
    "data.dataset.analyze",
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
}


@dataclass(frozen=True)
class PlannedStep:
    tool_id: str
    title: str
    params: dict[str, Any]


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _has_delivery_intent(text: str) -> bool:
    lowered = str(text or "").lower()
    return _has_any(
        lowered,
        (
            "send",
            "sent",
            "sending",
            "deliver",
            "delivered",
            "delivery",
            "email",
            "mail",
            "share",
            "forward",
        ),
    )


def _has_location_intent(text: str) -> bool:
    lowered = str(text or "").lower()
    return _has_any(
        lowered,
        (
            "where",
            "location",
            "located",
            "find them",
            "found in",
            "founded in",
            "based in",
            "headquarter",
            "headquarters",
            "hq",
            "address",
            "office",
            "offices",
            "country",
            "city",
        ),
    )


def is_deep_research_request(request: ChatRequest) -> bool:
    text = f"{request.message.lower()} {(request.agent_goal or '').lower()}".strip()
    if request.agent_mode != "company_agent":
        return False
    return _has_any(
        text,
        (
            "research",
            "deep research",
            "analyze",
            "analysis",
            "market",
            "competitor",
            "online",
            "website",
            "find companies",
        ),
    )


def _extract_url(text: str) -> str:
    match = URL_RE.search(text)
    return match.group(0).strip() if match else ""


def _extract_email(text: str) -> str:
    match = EMAIL_RE.search(text)
    return match.group(1).strip() if match else ""


def _sanitize_search_query(text: str, *, fallback_url: str = "") -> str:
    sanitized = EMAIL_RE.sub("", text or "")
    sanitized = URL_RE.sub("", sanitized)
    sanitized = " ".join(sanitized.split())
    if sanitized:
        return sanitized
    if fallback_url:
        host = (urlparse(fallback_url).hostname or "").strip()
        if host:
            return f"site:{host} company overview services"
    return "company overview services"


def _preferred_highlight_color(text: str) -> str:
    lowered = str(text or "").lower()
    if "green" in lowered:
        return "green"
    return "yellow"


def _intent_signals(request: ChatRequest) -> dict[str, Any]:
    message = str(request.message or "").strip()
    goal = str(request.agent_goal or "").strip()
    combined = f"{message} {goal}".strip()
    lower_message = message.lower()
    lower_combined = combined.lower()
    url = _extract_url(combined)
    recipient = _extract_email(combined)
    explicit_web_discovery = _has_any(
        lower_message,
        (
            "online",
            "find companies",
            "competitor",
            "market",
            "search",
            "sources",
        ),
    )
    wants_location_info = _has_location_intent(lower_combined)
    wants_send = _has_delivery_intent(lower_combined)
    wants_report = _has_any(lower_combined, ("report", "summary", "analysis", "analyze"))
    wants_highlight_words = _has_any(
        lower_combined,
        (
            "highlight",
            "highlights",
            "copied words",
            "copy words",
            "mark words",
            "yellow",
            "green",
        ),
    )
    wants_docs_output = _has_any(lower_combined, ("docs", "doc", "document"))
    wants_file_scope = _has_any(lower_combined, ("file", "files", "pdf", "document"))
    return {
        "url": url,
        "recipient_email": recipient,
        "explicit_web_discovery": explicit_web_discovery,
        "wants_location_info": wants_location_info,
        "wants_send": wants_send,
        "wants_report": wants_report,
        "wants_highlight_words": wants_highlight_words,
        "wants_docs_output": wants_docs_output,
        "wants_file_scope": wants_file_scope,
        "highlight_color": _preferred_highlight_color(lower_combined),
    }


def _sort_steps(steps: list[PlannedStep]) -> list[PlannedStep]:
    priorities = {
        "browser.playwright.inspect": 5,
        "documents.highlight.extract": 8,
        "workspace.docs.research_notes": 10,
        "workspace.sheets.track_step": 15,
        "marketing.web_research": 30,
        "marketing.local_discovery": 35,
        "marketing.competitor_profile": 40,
        "data.dataset.analyze": 45,
        "report.generate": 70,
        "docs.create": 72,
        "workspace.docs.fill_template": 74,
        "gmail.draft": 82,
        "email.draft": 82,
        "gmail.send": 88,
        "email.send": 88,
    }
    decorated = []
    for idx, step in enumerate(steps):
        decorated.append((priorities.get(step.tool_id, 60), idx, step))
    decorated.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in decorated]


def _normalize_steps(request: ChatRequest, steps: list[PlannedStep]) -> list[PlannedStep]:
    signals = _intent_signals(request)
    url = str(signals.get("url") or "")
    recipient = str(signals.get("recipient_email") or "")
    explicit_web_discovery = bool(signals.get("explicit_web_discovery"))
    wants_location_info = bool(signals.get("wants_location_info"))
    wants_send = bool(signals.get("wants_send"))
    wants_report = bool(signals.get("wants_report"))
    wants_highlight_words = bool(signals.get("wants_highlight_words"))
    wants_docs_output = bool(signals.get("wants_docs_output"))
    wants_file_scope = bool(signals.get("wants_file_scope"))
    highlight_color = str(signals.get("highlight_color") or "yellow")
    company_agent_mode = request.agent_mode == "company_agent"

    normalized: list[PlannedStep] = []
    for step in steps:
        params = dict(step.params)
        if step.tool_id == "browser.playwright.inspect" and url:
            params.setdefault("url", url)
        if step.tool_id == "browser.playwright.inspect":
            params.setdefault("highlight_color", highlight_color)
        if step.tool_id == "documents.highlight.extract":
            params.setdefault("highlight_color", highlight_color)
        if step.tool_id == "marketing.web_research":
            if wants_location_info and url:
                host = (urlparse(url).hostname or "").strip()
                query = (
                    f"site:{host} company headquarters location address offices where located"
                    if host
                    else _sanitize_search_query(str(params.get("query") or request.message), fallback_url=url)
                )
            else:
                query = _sanitize_search_query(
                    str(params.get("query") or request.message),
                    fallback_url=url,
                )
            params["query"] = rewrite_search_query(
                query=query,
                request=request,
                fallback_url=url,
            )
        if step.tool_id == "report.generate":
            params.setdefault("title", "Website Analysis Report")
            if url:
                host = (urlparse(url).hostname or url).strip()
                if wants_location_info:
                    params["summary"] = (
                        f"Identify where this company is located (headquarters, offices, and address signals) "
                        f"using evidence from {host}, then prepare a client-facing report."
                    )
                else:
                    params["summary"] = (
                        f"Analyze what this company does from {host} and prepare a client-facing report."
                    )
        if step.tool_id in ("gmail.draft", "gmail.send", "email.draft", "email.send") and recipient:
            params.setdefault("to", recipient)
        if step.tool_id == "docs.create" and wants_highlight_words:
            params.setdefault("include_copied_highlights", True)
        normalized.append(PlannedStep(tool_id=step.tool_id, title=step.title, params=params))

    if url and not explicit_web_discovery and not wants_location_info:
        normalized = [step for step in normalized if step.tool_id != "marketing.web_research"]

    if wants_location_info:
        has_web_research = any(step.tool_id == "marketing.web_research" for step in normalized)
        if not has_web_research:
            location_query = _sanitize_search_query(request.message, fallback_url=url)
            if url:
                host = (urlparse(url).hostname or "").strip()
                if host:
                    location_query = (
                        f"site:{host} headquarters location address offices where is the company based"
                    )
            normalized.append(
                PlannedStep(
                    tool_id="marketing.web_research",
                    title="Research company location signals",
                    params={"query": rewrite_search_query(query=location_query, request=request, fallback_url=url)},
                )
            )
        has_browser = any(step.tool_id == "browser.playwright.inspect" for step in normalized)
        if url and not has_browser:
            normalized.insert(
                0,
                PlannedStep(
                    tool_id="browser.playwright.inspect",
                    title="Inspect provided website in live browser",
                    params={"url": url, "highlight_color": highlight_color},
                ),
            )

    if company_agent_mode:
        normalized = [
            step
            for step in normalized
            if step.tool_id not in ("gmail.draft", "gmail.send", "email.draft", "email.send")
        ]

    if recipient and wants_send and not company_agent_mode:
        has_draft = any(step.tool_id in ("gmail.draft", "email.draft") for step in normalized)
        has_send = any(step.tool_id in ("gmail.send", "email.send") for step in normalized)
        if not has_draft:
            normalized.append(
                PlannedStep(
                    tool_id="gmail.draft",
                    title="Create Gmail draft",
                    params={"to": recipient},
                )
            )
        if not has_send:
            normalized.append(
                PlannedStep(
                    tool_id="gmail.send",
                    title="Send Gmail message",
                    params={"to": recipient},
                )
            )

    if wants_report and not any(step.tool_id == "report.generate" for step in normalized):
        normalized.append(
            PlannedStep(
                tool_id="report.generate",
                title="Generate report draft",
                params={"summary": request.message},
            )
        )

    if wants_highlight_words:
        has_browser = any(step.tool_id == "browser.playwright.inspect" for step in normalized)
        if url and not has_browser:
            normalized.insert(
                0,
                PlannedStep(
                    tool_id="browser.playwright.inspect",
                    title="Inspect provided website in live browser",
                    params={"url": url, "highlight_color": highlight_color},
                ),
            )
        if wants_file_scope and not any(step.tool_id == "documents.highlight.extract" for step in normalized):
            normalized.append(
                PlannedStep(
                    tool_id="documents.highlight.extract",
                    title="Highlight words in selected files",
                    params={"highlight_color": highlight_color},
                )
            )
        if wants_docs_output:
            has_docs_write = any(
                step.tool_id in ("docs.create", "workspace.docs.research_notes") for step in normalized
            )
            if not has_docs_write:
                normalized.append(
                    PlannedStep(
                        tool_id="docs.create",
                        title="Create document with copied highlights",
                        params={
                            "title": "Copied Highlights",
                            "body": "Captured highlights from files and websites.",
                            "include_copied_highlights": True,
                        },
                    )
                )

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

    return _sort_steps(deduped)


def _augment_for_deep_research(request: ChatRequest, steps: list[PlannedStep]) -> list[PlannedStep]:
    if not is_deep_research_request(request):
        return _normalize_steps(request, steps)

    enriched = list(steps)
    message_preview = " ".join(request.message.split())[:72] or "Deep Research"
    intent = _intent_signals(request)
    direct_url = str(intent.get("url") or "")
    explicit_web_discovery = bool(intent.get("explicit_web_discovery"))

    has_web = any(step.tool_id == "marketing.web_research" for step in enriched)
    if not has_web and (not direct_url or explicit_web_discovery):
        enriched.insert(
            0,
            PlannedStep(
                tool_id="marketing.web_research",
                title="Search online sources",
                params={"query": request.message},
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
                params={"url": direct_url},
            ),
        )

    lower_message = request.message.lower()
    wants_workspace_logging = _has_any(
        lower_message,
        (
            "google docs",
            "google sheets",
            "docs",
            "sheet",
            "sheets",
            "tracker",
            "notebook",
            "track step",
            "log step",
        ),
    )
    if wants_workspace_logging:
        kickoff = [
            PlannedStep(
                tool_id="workspace.docs.research_notes",
                title="Open research notebook",
                params={
                    "title": f"Maia Deep Research - {message_preview}",
                    "note": f"Research goal: {request.message.strip()}",
                },
            ),
            PlannedStep(
                tool_id="workspace.sheets.track_step",
                title="Initialize step tracker",
                params={
                    "step_name": "Run started",
                    "status": "started",
                    "detail": "Deep research run initialized",
                },
            ),
        ]
        enriched = kickoff + enriched

    return _normalize_steps(request, enriched)


def _build_semantic_fallback_steps(request: ChatRequest) -> list[PlannedStep]:
    """LLM-intent fallback when the dedicated planner returns no rows."""
    heuristic = _intent_signals(request)
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
    preferred_format = str(llm_intent.get("preferred_format") or "").strip().lower()

    requires_web = bool(llm_intent.get("requires_web_inspection"))
    if target_url:
        requires_web = True
    requires_delivery = bool(llm_intent.get("requires_delivery")) and bool(delivery_email)
    requested_report = bool(llm_intent.get("requested_report")) or company_agent_mode

    steps: list[PlannedStep] = []
    if target_url:
        steps.append(
            PlannedStep(
                tool_id="browser.playwright.inspect",
                title="Inspect provided website in live browser",
                params={"url": target_url},
            )
        )
    elif requires_web:
        steps.append(
            PlannedStep(
                tool_id="marketing.web_research",
                title="Search online sources",
                params={"query": objective or request.message},
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

    if any(token in preferred_format for token in ("doc", "document")):
        steps.append(
            PlannedStep(
                tool_id="docs.create",
                title="Create structured document draft",
                params={"title": "Company Draft", "body": objective or request.message},
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


def build_plan(request: ChatRequest) -> list[PlannedStep]:
    prompt = str(request.message or "").lower().strip()
    goal = str(request.agent_goal or "").lower().strip()
    text = prompt if prompt else goal
    steps: list[PlannedStep] = []
    company_agent_mode = request.agent_mode == "company_agent"
    llm_rows = plan_with_llm(request=request, allowed_tool_ids=LLM_ALLOWED_TOOL_IDS)
    if llm_rows:
        llm_rows = optimize_plan_rows(
            request=request,
            rows=llm_rows,
            allowed_tool_ids=LLM_ALLOWED_TOOL_IDS,
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
                )
            )
        if llm_steps:
            return _augment_for_deep_research(request, llm_steps)

    semantic_fallback_steps = _build_semantic_fallback_steps(request)
    if semantic_fallback_steps:
        return _augment_for_deep_research(request, semantic_fallback_steps)

    if _has_any(text, ("research", "internet", "competitor", "market", "online", "sources")):
        steps.append(
            PlannedStep(
                tool_id="marketing.web_research",
                title="Search online sources",
                params={"query": request.message},
            )
        )
    if _has_any(text, ("local business", "nearby", "places", "geocode", "distance")):
        steps.append(
            PlannedStep(
                tool_id="marketing.local_discovery",
                title="Discover local companies",
                params={"query": request.message},
            )
        )
    if _has_any(text, ("geocode", "coordinates", "lat", "lng")):
        steps.append(
            PlannedStep(
                tool_id="maps.geocode",
                title="Geocode address",
                params={},
            )
        )
    if _has_any(text, ("distance matrix", "travel time", "route distance")):
        steps.append(
            PlannedStep(
                tool_id="maps.distance_matrix",
                title="Calculate route distances",
                params={},
            )
        )
    if _has_any(text, ("browse ", "open website", "inspect website", "playwright")):
        steps.append(
            PlannedStep(
                tool_id="browser.playwright.inspect",
                title="Inspect website in live browser",
                params={},
            )
        )
    if "competitor" in text or "positioning" in text:
        steps.append(
            PlannedStep(
                tool_id="marketing.competitor_profile",
                title="Build competitor profile",
                params={},
            )
        )
    if _has_any(text, ("google ads", "ads", "campaign", "roas", "ctr")):
        steps.append(
            PlannedStep(
                tool_id="ads.google.performance",
                title="Analyze ad performance",
                params={},
            )
        )
    if _has_any(text, ("doc", "document", "proposal", "brief", "write report", "create report")):
        steps.append(
            PlannedStep(
                tool_id="docs.create",
                title="Create structured document draft",
                params={"title": "Company Draft", "body": request.message},
            )
        )
    if _has_any(text, ("csv", "dataset", "analyze data", "table", "excel")):
        steps.append(
            PlannedStep(
                tool_id="data.dataset.analyze",
                title="Analyze provided dataset",
                params={},
            )
        )
    if "invoice" in text or "billing" in text:
        steps.append(
            PlannedStep(
                tool_id="invoice.create",
                title="Draft invoice",
                params={},
            )
        )
        if _has_delivery_intent(text):
            steps.append(
                PlannedStep(
                    tool_id="invoice.send",
                    title="Send invoice",
                    params={},
                )
            )
    if not company_agent_mode and "email" in text and "gmail" not in text:
        steps.append(
            PlannedStep(
                tool_id="email.draft",
                title="Draft email",
                params={},
            )
        )
        if _has_delivery_intent(text):
            steps.append(
                PlannedStep(
                    tool_id="email.send",
                    title="Send email",
                    params={},
                )
            )
    if "gmail" in text:
        if not company_agent_mode:
            steps.append(
                PlannedStep(
                    tool_id="gmail.draft",
                    title="Create Gmail draft",
                    params={},
                )
            )
            if _has_delivery_intent(text):
                steps.append(
                    PlannedStep(
                        tool_id="gmail.send",
                        title="Send Gmail message",
                        params={},
                    )
                )
        if _has_any(text, ("search", "inbox", "mailbox")):
            steps.append(
                PlannedStep(
                    tool_id="gmail.search",
                    title="Search Gmail mailbox",
                    params={},
                )
            )
    if _has_any(text, ("validate email", "email verify", "bounce")):
        steps.append(
            PlannedStep(
                tool_id="email.validate",
                title="Validate email quality",
                params={},
            )
        )
    if "slack" in text:
        steps.append(
            PlannedStep(
                tool_id="slack.post_message",
                title="Post update to Slack",
                params={},
            )
        )
    if _has_any(text, ("calendar", "meeting", "reminder", "schedule")):
        steps.append(
            PlannedStep(
                tool_id="calendar.create_event",
                title="Create calendar event",
                params={},
            )
        )
    if _has_any(text, ("ga4", "google analytics", "analytics", "sessions", "traffic")):
        steps.append(
            PlannedStep(
                tool_id="analytics.ga4.report",
                title="Run GA4 analytics report",
                params={},
            )
        )
    if _has_any(text, ("chart", "graph", "plot", "visual report")):
        steps.append(
            PlannedStep(
                tool_id="analytics.chart.generate",
                title="Generate chart artifact",
                params={},
            )
        )
    if _has_any(text, ("google drive", "drive files", "search drive")):
        steps.append(
            PlannedStep(
                tool_id="workspace.drive.search",
                title="Search Google Drive",
                params={"query": request.message},
            )
        )
    if _has_any(text, ("google sheet", "sheets", "append row", "crm sheet")):
        steps.append(
            PlannedStep(
                tool_id="workspace.sheets.append",
                title="Append rows to Google Sheets",
                params={},
            )
        )
    if _has_any(text, ("template", "placeholder", "fill doc")):
        steps.append(
            PlannedStep(
                tool_id="workspace.docs.fill_template",
                title="Fill Google Docs template",
                params={},
            )
        )
    if _has_any(text, ("report", "summary", "weekly", "monthly")):
        steps.append(
            PlannedStep(
                tool_id="report.generate",
                title="Generate report draft",
                params={"summary": request.message},
            )
        )

    if not steps:
        steps = [
            PlannedStep(
                tool_id="marketing.web_research",
                title="Search relevant sources",
                params={"query": request.message},
            ),
            PlannedStep(
                tool_id="report.generate",
                title="Create concise executive output",
                params={"summary": request.message},
            ),
        ]
    candidate_rows = [
        {"tool_id": step.tool_id, "title": step.title, "params": dict(step.params)}
        for step in steps
    ]
    optimized_rows = optimize_plan_rows(
        request=request,
        rows=candidate_rows,
        allowed_tool_ids=LLM_ALLOWED_TOOL_IDS,
    )
    if optimized_rows:
        steps = [
            PlannedStep(
                tool_id=str(row.get("tool_id") or "").strip(),
                title=str(row.get("title") or "").strip() or str(row.get("tool_id") or "Planned step"),
                params=dict(row.get("params")) if isinstance(row.get("params"), dict) else {},
            )
            for row in optimized_rows
            if str(row.get("tool_id") or "").strip()
        ] or steps
    return _augment_for_deep_research(request, steps)


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
