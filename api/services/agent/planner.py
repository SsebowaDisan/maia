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
    "browser.contact_form.send",
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
    why_this_step: str = ""
    expected_evidence: tuple[str, ...] = ()


def is_deep_research_request(request: ChatRequest) -> bool:
    return request.agent_mode == "company_agent" and bool(str(request.agent_goal or "").strip())


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
    return "yellow"


def _intent_signals(request: ChatRequest) -> dict[str, Any]:
    message = str(request.message or "").strip()
    goal = str(request.agent_goal or "").strip()
    combined = f"{message} {goal}".strip()
    url = _extract_url(combined)
    recipient = _extract_email(combined)
    return {
        "url": url,
        "recipient_email": recipient,
        "explicit_web_discovery": False,
        "wants_location_info": False,
        "wants_send": bool(recipient),
        "wants_report": False,
        "wants_highlight_words": False,
        "wants_contact_form": False,
        "wants_docs_output": False,
        "wants_file_scope": False,
        "highlight_color": _preferred_highlight_color(combined),
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
        "browser.contact_form.send": 86,
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
    highlight_color = str(signals.get("highlight_color") or "yellow")
    company_agent_mode = request.agent_mode == "company_agent"
    has_highlight_extract = any(step.tool_id == "documents.highlight.extract" for step in steps)

    normalized: list[PlannedStep] = []
    for step in steps:
        params = dict(step.params)
        if step.tool_id == "browser.playwright.inspect":
            if url:
                params.setdefault("url", url)
            params.setdefault("highlight_color", highlight_color)
        if step.tool_id == "documents.highlight.extract":
            params.setdefault("highlight_color", highlight_color)
        if step.tool_id == "marketing.web_research":
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
            params.setdefault("summary", request.message)
        if step.tool_id in ("gmail.draft", "gmail.send", "email.draft", "email.send") and recipient:
            params.setdefault("to", recipient)
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

    return _sort_steps(deduped)


def _augment_for_deep_research(request: ChatRequest, steps: list[PlannedStep]) -> list[PlannedStep]:
    if not is_deep_research_request(request):
        return _normalize_steps(request, steps)

    enriched = list(steps)
    intent = _intent_signals(request)
    direct_url = str(intent.get("url") or "")

    has_web = any(step.tool_id == "marketing.web_research" for step in enriched)
    if not has_web and not direct_url:
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
def build_plan(request: ChatRequest) -> list[PlannedStep]:
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
            return _augment_for_deep_research(request, llm_steps)

    semantic_fallback_steps = _build_semantic_fallback_steps(request)
    if semantic_fallback_steps:
        return _augment_for_deep_research(request, semantic_fallback_steps)

    signals = _intent_signals(request)
    target_url = str(signals.get("url") or "")
    recipient = str(signals.get("recipient_email") or "")
    if target_url:
        steps.append(
            PlannedStep(
                tool_id="browser.playwright.inspect",
                title="Inspect provided website in live browser",
                params={"url": target_url},
            )
        )
    else:
        steps.append(
            PlannedStep(
                tool_id="marketing.web_research",
                title="Search online sources",
                params={"query": request.message},
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
        allowed_tool_ids=LLM_ALLOWED_TOOL_IDS,
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
