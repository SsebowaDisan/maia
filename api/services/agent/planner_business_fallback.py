from __future__ import annotations

import re
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.tools.business_workflow_helpers import (
    amount_from_text,
    email_from_text,
    invoice_number_from_text,
)


def _route_params_from_text(text: str) -> dict[str, Any]:
    compact = " ".join(str(text or "").split()).strip()
    match = re.search(
        r"\bfrom\s+(?P<origin>.+?)\s+to\s+(?P<destinations>.+?)(?:[.?!]|$)",
        compact,
        flags=re.IGNORECASE,
    )
    if not match:
        return {}
    origin = str(match.group("origin") or "").strip()
    raw_destinations = str(match.group("destinations") or "").strip()
    destinations = [
        part.strip()
        for part in re.split(r",|;|\band\b", raw_destinations, flags=re.IGNORECASE)
        if part.strip()
    ]
    if not origin or not destinations:
        return {}
    return {"origin": origin, "destinations": destinations, "mode": "driving"}


def _invoice_params_from_text(text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    number = invoice_number_from_text(text)
    if number:
        params["invoice_number"] = number
    amount = amount_from_text(text)
    if amount is not None:
        params["amount"] = amount
    recipient = email_from_text(text)
    if recipient:
        params["to"] = recipient
    lowered = text.lower()
    if "send invoice" in lowered or "email invoice" in lowered or "mail invoice" in lowered:
        params["send"] = True
    return params


def build_business_fallback_rows(request: ChatRequest) -> list[dict[str, Any]]:
    text = " ".join(
        [
            str(request.message or "").strip(),
            str(request.agent_goal or "").strip(),
        ]
    ).strip()
    lowered = text.lower()
    if not lowered:
        return []

    rows: list[dict[str, Any]] = []
    if (
        ("route" in lowered or "travel time" in lowered or "distance matrix" in lowered)
        and (" from " in f" {lowered} ")
        and (" to " in f" {lowered} ")
    ):
        rows.append(
            {
                "tool_id": "business.route_plan",
                "title": "Create business route plan",
                "params": _route_params_from_text(str(request.message or "")),
            }
        )

    if "ga4" in lowered and (
        "weekly" in lowered
        or "sheet" in lowered
        or "sheets" in lowered
        or "kpi" in lowered
    ):
        rows.append(
            {
                "tool_id": "business.ga4_kpi_sheet_report",
                "title": "Generate GA4 KPI report in Google Sheets",
                "params": {"sheet_range": "Tracker!A1"},
            }
        )

    if ("incident" in lowered or "outage" in lowered or "alert" in lowered) and (
        "cloud" in lowered or "logging" in lowered or "gcp" in lowered
    ) and ("email" in lowered or "mail" in lowered):
        params: dict[str, Any] = {"send": True}
        recipient = email_from_text(text)
        if recipient:
            params["to"] = recipient
        rows.append(
            {
                "tool_id": "business.cloud_incident_digest_email",
                "title": "Send cloud incident digest email",
                "params": params,
            }
        )

    if "invoice" in lowered:
        rows.append(
            {
                "tool_id": "business.invoice_workflow",
                "title": "Run invoice workflow",
                "params": _invoice_params_from_text(text),
            }
        )

    if (
        "meeting" in lowered
        or "schedule meeting" in lowered
        or "calendar invite" in lowered
        or ("calendar" in lowered and "schedule" in lowered)
    ):
        params: dict[str, Any] = {}
        email = email_from_text(text)
        if email:
            params["attendees"] = [email]
        rows.append(
            {
                "tool_id": "business.meeting_scheduler",
                "title": "Schedule meeting workflow",
                "params": params,
            }
        )

    if "proposal" in lowered or "rfp" in lowered or "quotation" in lowered or "quote" in lowered:
        params = {}
        recipient = email_from_text(text)
        if recipient:
            params["to"] = recipient
        rows.append(
            {
                "tool_id": "business.proposal_workflow",
                "title": "Create proposal workflow",
                "params": params,
            }
        )

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        tool_id = str(row.get("tool_id") or "").strip()
        if not tool_id or tool_id in seen:
            continue
        seen.add(tool_id)
        deduped.append(row)
    return deduped
