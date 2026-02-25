from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlparse

from api.schemas import ChatRequest

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


@dataclass(frozen=True)
class PlannedStep:
    tool_id: str
    title: str
    params: dict[str, Any]


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


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
    wants_send = _has_any(lower_combined, ("send", "deliver", "email"))
    wants_report = _has_any(lower_combined, ("report", "summary", "analysis", "analyze"))
    return {
        "url": url,
        "recipient_email": recipient,
        "explicit_web_discovery": explicit_web_discovery,
        "wants_send": wants_send,
        "wants_report": wants_report,
    }


def _sort_steps(steps: list[PlannedStep]) -> list[PlannedStep]:
    priorities = {
        "workspace.docs.research_notes": 10,
        "workspace.sheets.track_step": 15,
        "browser.playwright.inspect": 20,
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
    wants_send = bool(signals.get("wants_send"))
    wants_report = bool(signals.get("wants_report"))

    normalized: list[PlannedStep] = []
    for step in steps:
        params = dict(step.params)
        if step.tool_id == "browser.playwright.inspect" and url:
            params.setdefault("url", url)
        if step.tool_id == "marketing.web_research":
            params["query"] = _sanitize_search_query(
                str(params.get("query") or request.message),
                fallback_url=url,
            )
        if step.tool_id == "report.generate":
            params.setdefault("title", "Website Analysis Report")
            if url:
                host = (urlparse(url).hostname or url).strip()
                params["summary"] = (
                    f"Analyze what this company does from {host} and prepare a client-facing report."
                )
        if step.tool_id in ("gmail.draft", "gmail.send", "email.draft", "email.send") and recipient:
            params.setdefault("to", recipient)
        normalized.append(PlannedStep(tool_id=step.tool_id, title=step.title, params=params))

    if url and not explicit_web_discovery:
        normalized = [step for step in normalized if step.tool_id != "marketing.web_research"]

    if recipient and wants_send:
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

    if direct_url and not any(step.tool_id == "browser.playwright.inspect" for step in enriched):
        enriched.insert(
            1,
            PlannedStep(
                tool_id="browser.playwright.inspect",
                title="Inspect provided website in live browser",
                params={"url": direct_url},
            ),
        )

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
    return _normalize_steps(request, kickoff + enriched)


def build_plan(request: ChatRequest) -> list[PlannedStep]:
    prompt = str(request.message or "").lower().strip()
    goal = str(request.agent_goal or "").lower().strip()
    text = prompt if prompt else goal
    steps: list[PlannedStep] = []

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
        if _has_any(text, ("send", "deliver")):
            steps.append(
                PlannedStep(
                    tool_id="invoice.send",
                    title="Send invoice",
                    params={},
                )
            )
    if "email" in text and "gmail" not in text:
        steps.append(
            PlannedStep(
                tool_id="email.draft",
                title="Draft email",
                params={},
            )
        )
        if "send" in text:
            steps.append(
                PlannedStep(
                    tool_id="email.send",
                    title="Send email",
                    params={},
                )
            )
    if "gmail" in text:
        steps.append(
            PlannedStep(
                tool_id="gmail.draft",
                title="Create Gmail draft",
                params={},
            )
        )
        if "send" in text:
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
