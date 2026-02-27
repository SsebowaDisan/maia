from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ACTION_CLASS_READ = "read"
ACTION_CLASS_DRAFT = "draft"
ACTION_CLASS_EXECUTE = "execute"
ActionClass = Literal["read", "draft", "execute"]

ACCESS_MODE_RESTRICTED = "restricted"
ACCESS_MODE_FULL = "full_access"
AccessMode = Literal["restricted", "full_access"]

USER_ROLE_OWNER = "owner"
USER_ROLE_ADMIN = "admin"
USER_ROLE_MEMBER = "member"
USER_ROLE_ANALYST = "analyst"
UserRole = Literal["owner", "admin", "member", "analyst"]


@dataclass(frozen=True)
class AgentToolCapability:
    domain: str
    tool_id: str
    action_class: ActionClass
    minimum_role: UserRole
    description: str
    execution_policy: Literal["auto_execute", "confirm_before_execute"] = (
        "confirm_before_execute"
    )


@dataclass(frozen=True)
class AgentAccessContext:
    role: UserRole
    access_mode: AccessMode
    full_access_enabled: bool
    tenant_id: str


_ROLE_PRIORITY: dict[UserRole, int] = {
    USER_ROLE_ANALYST: 10,
    USER_ROLE_MEMBER: 20,
    USER_ROLE_ADMIN: 30,
    USER_ROLE_OWNER: 40,
}

_CAPABILITY_MATRIX: tuple[AgentToolCapability, ...] = (
    AgentToolCapability(
        domain="marketing_research",
        tool_id="marketing.web_research",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_ANALYST,
        description="Search and summarize market/competitor intelligence with sources.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="marketing_research",
        tool_id="marketing.competitor_profile",
        action_class=ACTION_CLASS_DRAFT,
        minimum_role=USER_ROLE_MEMBER,
        description="Generate competitor profiles and positioning gap analysis.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="marketing_research",
        tool_id="marketing.local_discovery",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_ANALYST,
        description="Discover nearby companies via Places/Geocoding/Distance APIs.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="marketing_research",
        tool_id="maps.geocode",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_ANALYST,
        description="Convert addresses into geocoordinates using Google Geocoding API.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="marketing_research",
        tool_id="maps.distance_matrix",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_ANALYST,
        description="Compute route distance/time with Google Distance Matrix API.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="marketing_research",
        tool_id="browser.playwright.inspect",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_ANALYST,
        description="Inspect live websites through Playwright browser automation.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="outreach",
        tool_id="browser.contact_form.send",
        action_class=ACTION_CLASS_EXECUTE,
        minimum_role=USER_ROLE_ADMIN,
        description="Fill and submit a website contact form for approved outreach.",
        execution_policy="confirm_before_execute",
    ),
    AgentToolCapability(
        domain="email_ops",
        tool_id="email.draft",
        action_class=ACTION_CLASS_DRAFT,
        minimum_role=USER_ROLE_MEMBER,
        description="Draft contextual company emails.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="email_ops",
        tool_id="email.send",
        action_class=ACTION_CLASS_EXECUTE,
        minimum_role=USER_ROLE_ADMIN,
        description="Send email through configured provider.",
        execution_policy="confirm_before_execute",
    ),
    AgentToolCapability(
        domain="email_ops",
        tool_id="gmail.draft",
        action_class=ACTION_CLASS_DRAFT,
        minimum_role=USER_ROLE_MEMBER,
        description="Create Gmail drafts using Gmail API.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="email_ops",
        tool_id="gmail.send",
        action_class=ACTION_CLASS_EXECUTE,
        minimum_role=USER_ROLE_ADMIN,
        description="Send Gmail messages via Gmail API.",
        execution_policy="confirm_before_execute",
    ),
    AgentToolCapability(
        domain="email_ops",
        tool_id="gmail.search",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_MEMBER,
        description="Search mailbox through Gmail API.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="email_ops",
        tool_id="email.validate",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_MEMBER,
        description="Validate deliverability of email addresses before outreach.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="ads_analysis",
        tool_id="ads.google.performance",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_ANALYST,
        description="Analyze Google Ads campaign performance and recommendations.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="data_analysis",
        tool_id="data.dataset.analyze",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_ANALYST,
        description="Run constrained analysis over indexed and tabular data.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="reporting",
        tool_id="report.generate",
        action_class=ACTION_CLASS_DRAFT,
        minimum_role=USER_ROLE_MEMBER,
        description="Generate executive summaries and recurring reports.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="analytics",
        tool_id="analytics.ga4.report",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_ANALYST,
        description="Run GA4 analytics reports with dimensions and metrics.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="analytics",
        tool_id="analytics.chart.generate",
        action_class=ACTION_CLASS_DRAFT,
        minimum_role=USER_ROLE_MEMBER,
        description="Generate chart artifacts for reporting workflows.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="document_ops",
        tool_id="docs.create",
        action_class=ACTION_CLASS_DRAFT,
        minimum_role=USER_ROLE_MEMBER,
        description="Create and populate structured company documents.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="document_ops",
        tool_id="documents.highlight.extract",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_ANALYST,
        description="Highlight and copy relevant words from selected indexed files.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="document_ops",
        tool_id="workspace.docs.fill_template",
        action_class=ACTION_CLASS_DRAFT,
        minimum_role=USER_ROLE_MEMBER,
        description="Fill Google Docs templates with dynamic placeholders.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="document_ops",
        tool_id="workspace.docs.research_notes",
        action_class=ACTION_CLASS_DRAFT,
        minimum_role=USER_ROLE_MEMBER,
        description="Append deep research notes into a Google Docs notebook.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="document_ops",
        tool_id="workspace.drive.search",
        action_class=ACTION_CLASS_READ,
        minimum_role=USER_ROLE_MEMBER,
        description="Search and reference Google Drive files.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="document_ops",
        tool_id="workspace.sheets.append",
        action_class=ACTION_CLASS_EXECUTE,
        minimum_role=USER_ROLE_ADMIN,
        description="Append rows into Google Sheets for CRM and KPI tracking.",
        execution_policy="confirm_before_execute",
    ),
    AgentToolCapability(
        domain="document_ops",
        tool_id="workspace.sheets.track_step",
        action_class=ACTION_CLASS_EXECUTE,
        minimum_role=USER_ROLE_MEMBER,
        description="Track deep research step completion in Google Sheets.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="scheduling",
        tool_id="calendar.create_event",
        action_class=ACTION_CLASS_EXECUTE,
        minimum_role=USER_ROLE_ADMIN,
        description="Create Google Calendar meeting/follow-up events.",
        execution_policy="confirm_before_execute",
    ),
    AgentToolCapability(
        domain="invoice",
        tool_id="invoice.create",
        action_class=ACTION_CLASS_DRAFT,
        minimum_role=USER_ROLE_MEMBER,
        description="Draft invoice payload and render invoice document.",
        execution_policy="auto_execute",
    ),
    AgentToolCapability(
        domain="invoice",
        tool_id="invoice.send",
        action_class=ACTION_CLASS_EXECUTE,
        minimum_role=USER_ROLE_ADMIN,
        description="Send invoice via email/accounting connector.",
        execution_policy="confirm_before_execute",
    ),
    AgentToolCapability(
        domain="workplace",
        tool_id="slack.post_message",
        action_class=ACTION_CLASS_EXECUTE,
        minimum_role=USER_ROLE_ADMIN,
        description="Post insights/alerts to Slack channels.",
        execution_policy="confirm_before_execute",
    ),
)


def get_capability_matrix() -> tuple[AgentToolCapability, ...]:
    return _CAPABILITY_MATRIX


def _safe_role(value: Any) -> UserRole:
    text = str(value or "").strip().lower()
    if text in _ROLE_PRIORITY:
        return text  # type: ignore[return-value]
    return USER_ROLE_MEMBER


def _safe_access_mode(value: Any) -> AccessMode:
    text = str(value or "").strip().lower()
    if text == ACCESS_MODE_FULL:
        return ACCESS_MODE_FULL
    return ACCESS_MODE_RESTRICTED


def build_access_context(
    *,
    user_id: str,
    settings: dict[str, Any],
) -> AgentAccessContext:
    role = _safe_role(settings.get("agent.user_role"))
    access_mode = _safe_access_mode(settings.get("agent.access_mode"))
    full_access_enabled = bool(settings.get("agent.full_access_enabled", False))
    tenant_id = str(settings.get("agent.tenant_id") or user_id)
    return AgentAccessContext(
        role=role,
        access_mode=access_mode,
        full_access_enabled=full_access_enabled,
        tenant_id=tenant_id,
    )


def has_required_role(context: AgentAccessContext, minimum_role: UserRole) -> bool:
    return _ROLE_PRIORITY[context.role] >= _ROLE_PRIORITY[minimum_role]


def resolve_execution_policy(
    capability: AgentToolCapability,
    context: AgentAccessContext,
) -> Literal["auto_execute", "confirm_before_execute"]:
    if (
        capability.action_class == ACTION_CLASS_EXECUTE
        and context.access_mode == ACCESS_MODE_FULL
        and context.full_access_enabled
    ):
        return "auto_execute"
    return capability.execution_policy
