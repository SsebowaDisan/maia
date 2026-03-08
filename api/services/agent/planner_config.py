from __future__ import annotations

from api.services.agent.google_api_catalog import GOOGLE_API_TOOL_IDS
from api.services.agent.llm_runtime import env_bool

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

CORE_FLOW_TOOL_IDS = {
    "browser.playwright.inspect",
    "web.dataset.adapter",
    "web.extract.structured",
    "documents.highlight.extract",
    "docs.create",
    "marketing.web_research",
    "report.generate",
}

RESEARCH_ONLY_BLOCKED_TOOL_IDS = {
    "email.draft",
    "email.send",
    "gmail.draft",
    "gmail.send",
    "business.cloud_incident_digest_email",
    "invoice.create",
    "invoice.send",
    "slack.post_message",
    "calendar.create_event",
}

DEFAULT_WEB_RESEARCH_PROVIDER = "brave_search"
DEFAULT_WEB_PROVIDER = "playwright_browser"


def planning_allowed_tool_ids(
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
    constrained = set(preferred).union(CORE_FLOW_TOOL_IDS)
    constrained = {
        tool_id
        for tool_id in constrained
        if tool_id in LLM_ALLOWED_TOOL_IDS
    }
    return constrained or set(LLM_ALLOWED_TOOL_IDS)
