from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from api.schemas import ChatRequest
from api.services.agent.llm_intent import detect_web_routing_mode
from api.services.agent.llm_plan_optimizer import rewrite_search_query
from api.services.agent.planner_helpers import intent_signals, sanitize_search_query

from .planner_config import (
    DEFAULT_WEB_PROVIDER,
    DEFAULT_WEB_RESEARCH_PROVIDER,
    RESEARCH_ONLY_BLOCKED_TOOL_IDS,
)
from .planner_models import PlannedStep


def host_from_url(url: str) -> str:
    try:
        host = str(urlparse(str(url or "").strip()).hostname or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


_PLACEHOLDER_HOSTS = {
    "example.com",
    "example.org",
    "example.net",
    "localhost",
    "127.0.0.1",
}


def _clean_http_urls(value: Any) -> list[str]:
    urls: list[str] = []
    rows = value if isinstance(value, list) else []
    for item in rows:
        text = " ".join(str(item or "").split()).strip()
        if not text.startswith(("http://", "https://")):
            continue
        if _is_placeholder_url(text):
            continue
        if text not in urls:
            urls.append(text)
    return urls


def _is_placeholder_url(url: str) -> bool:
    host = host_from_url(url)
    if not host:
        return True
    return host in _PLACEHOLDER_HOSTS or host.endswith(".example.com")


def request_has_selected_files(request: ChatRequest) -> bool:
    selection = request.index_selection if isinstance(request.index_selection, dict) else {}
    for selected in selection.values():
        mode = str(getattr(selected, "mode", "") or "").strip().lower()
        file_ids = getattr(selected, "file_ids", [])
        normalized_ids = [
            str(item).strip()
            for item in (file_ids if isinstance(file_ids, list) else [])
            if str(item).strip()
        ]
        if mode == "select" and normalized_ids:
            return True
    attachments = request.attachments if isinstance(request.attachments, list) else []
    for row in attachments:
        file_id = str(getattr(row, "file_id", "") or "").strip()
        if file_id:
            return True
    return False


def sort_steps(
    steps: list[PlannedStep],
    *,
    preferred_tool_ids: set[str] | None = None,
) -> list[PlannedStep]:
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
        "analytics.ga4.full_report": 43,
        "analytics.ga4.report": 44,
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


def normalize_steps(
    request: ChatRequest,
    steps: list[PlannedStep],
    *,
    preferred_tool_ids: set[str] | None = None,
    intent: dict[str, Any] | None = None,
    web_routing: dict[str, Any] | None = None,
    deep_research_mode: bool,
    company_agent_mode: bool,
) -> list[PlannedStep]:
    signals = intent if isinstance(intent, dict) else intent_signals(request)
    url = str(signals.get("url") or "")
    recipient = str(signals.get("recipient_email") or "")
    attachment_delivery_requested = bool(signals.get("wants_attachment_delivery"))
    highlight_color = str(signals.get("highlight_color") or "yellow")
    routing = web_routing if isinstance(web_routing, dict) else detect_web_routing_mode(
        message=request.message,
        agent_goal=request.agent_goal,
        heuristic=signals,
    )
    routing_mode = str(routing.get("routing_mode") or "").strip().lower()
    scrape_url_requested = routing_mode == "url_scrape"
    online_research_requested = routing_mode == "online_research"
    has_highlight_extract = any(step.tool_id == "documents.highlight.extract" for step in steps)
    has_selected_files = request_has_selected_files(request)

    normalized: list[PlannedStep] = []
    for step in steps:
        params = dict(step.params)
        drop_step = False
        if step.tool_id == "browser.playwright.inspect":
            candidate_urls = _clean_http_urls(
                params.get("candidate_urls") or params.get("urls") or params.get("source_urls") or []
            )
            if candidate_urls:
                params.setdefault("url", candidate_urls[0])
                params["candidate_urls"] = candidate_urls[:8]
                params["urls"] = candidate_urls[:8]
            if url:
                params.setdefault("url", url)
            params.setdefault("web_provider", DEFAULT_WEB_PROVIDER)
            params.setdefault("highlight_color", highlight_color)
            step_url = " ".join(str(params.get("url") or "").split()).strip()
            if not step_url or _is_placeholder_url(step_url):
                drop_step = not bool(url)
        if step.tool_id == "documents.highlight.extract":
            params.setdefault("highlight_color", highlight_color)
        if step.tool_id == "web.extract.structured":
            if url:
                params.setdefault("url", url)
            candidate_urls = _clean_http_urls(params.get("source_urls"))
            if candidate_urls:
                params.setdefault("url", candidate_urls[0])
                params.setdefault("candidate_urls", candidate_urls[:8])
            params.pop("source_urls", None)
            params.setdefault("extraction_goal", request.message)
            step_url = " ".join(str(params.get("url") or "").split()).strip()
            if not step_url or _is_placeholder_url(step_url):
                drop_step = not bool(url)
        if step.tool_id == "web.dataset.adapter":
            if url:
                params.setdefault("url", url)
            params.setdefault("goal", request.message)
            step_url = " ".join(str(params.get("url") or "").split()).strip()
            if not step_url or _is_placeholder_url(step_url):
                drop_step = not bool(url)
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
            if url and routing_mode == "url_scrape":
                scoped_host = host_from_url(url)
                if scoped_host:
                    params.setdefault("domain_scope", [scoped_host])
                    params.setdefault("domain_scope_mode", "strict")
                    params.setdefault("target_url", url)
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
        if step.tool_id == "workspace.docs.fill_template" and attachment_delivery_requested:
            params.setdefault("export_pdf", True)
        if step.tool_id in ("gmail.draft", "gmail.send") and attachment_delivery_requested:
            params.setdefault("attach_latest_report_pdf", True)
        if drop_step:
            continue
        normalized.append(
            PlannedStep(
                tool_id=step.tool_id,
                title=step.title,
                params=params,
                why_this_step=step.why_this_step,
                expected_evidence=step.expected_evidence,
            )
        )

    pdf_live_required = has_selected_files or bool(signals.get("wants_file_scope"))
    has_pdf_step = any(step.tool_id == "documents.highlight.extract" for step in normalized)
    if pdf_live_required and not has_pdf_step:
        insert_at = 1 if normalized and normalized[0].tool_id == "browser.playwright.inspect" else 0
        normalized.insert(
            insert_at,
            PlannedStep(
                tool_id="documents.highlight.extract",
                title="Highlight words in selected files",
                params={"highlight_color": highlight_color},
            ),
        )

    if scrape_url_requested and url:
        if not deep_research_mode:
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
        if deep_research_mode and not any(
            row.tool_id == "marketing.web_research" for row in normalized
        ):
            scoped_host = host_from_url(url)
            normalized.insert(
                1 if normalized and normalized[0].tool_id == "browser.playwright.inspect" else 0,
                PlannedStep(
                    tool_id="marketing.web_research",
                    title="Search online sources",
                    params={
                        "query": sanitize_search_query(request.message, fallback_url=url),
                        "provider": DEFAULT_WEB_RESEARCH_PROVIDER,
                        "allow_provider_fallback": False,
                        "domain_scope": [scoped_host] if scoped_host else [],
                        "domain_scope_mode": "strict" if scoped_host else "off",
                        "target_url": url,
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
    elif routing_mode == "none" and not url and not deep_research_mode:
        pruned: list[PlannedStep] = []
        for step in normalized:
            if step.tool_id not in (
                "marketing.web_research",
                "browser.playwright.inspect",
                "web.extract.structured",
                "web.dataset.adapter",
            ):
                pruned.append(step)
                continue
            step_url = " ".join(str(step.params.get("url") or "").split()).strip()
            if step_url.startswith(("http://", "https://")):
                pruned.append(step)
        normalized = pruned

    if has_selected_files and not url and not deep_research_mode:
        normalized = [
            step
            for step in normalized
            if step.tool_id
            not in (
                "marketing.web_research",
                "browser.playwright.inspect",
                "web.extract.structured",
                "web.dataset.adapter",
            )
        ]

    if company_agent_mode:
        normalized = [
            step
            for step in normalized
            if step.tool_id not in ("gmail.draft", "gmail.send", "email.draft", "email.send")
        ]
    if deep_research_mode:
        normalized = [
            step
            for step in normalized
            if step.tool_id not in RESEARCH_ONLY_BLOCKED_TOOL_IDS
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

    if not deduped:
        deduped.append(
            PlannedStep(
                tool_id="report.generate",
                title="Create concise executive output",
                params={"summary": request.message},
            )
        )

    return sort_steps(deduped, preferred_tool_ids=preferred_tool_ids)
