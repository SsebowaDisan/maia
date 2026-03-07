from __future__ import annotations

from dataclasses import dataclass

from .agent_roles import AgentRole, DEFAULT_AGENT_ROLE, list_agent_roles, normalize_agent_role


@dataclass(frozen=True, slots=True)
class AgentRoleContract:
    role: AgentRole
    summary: str
    allowed_tool_ids: frozenset[str]
    allowed_tool_prefixes: tuple[str, ...]
    primary_outputs: tuple[str, ...]
    verification_obligations: tuple[str, ...]


_ROLE_CONTRACTS: dict[AgentRole, AgentRoleContract] = {
    "conductor": AgentRoleContract(
        role="conductor",
        summary="Coordinates run state, checkpoints, and role transitions.",
        allowed_tool_ids=frozenset(),
        allowed_tool_prefixes=(),
        primary_outputs=("execution checkpoints", "role handoff decisions"),
        verification_obligations=("run remains resumable", "handoff state is persisted"),
    ),
    "planner": AgentRoleContract(
        role="planner",
        summary="Builds ordered role-owned steps with evidence expectations.",
        allowed_tool_ids=frozenset(),
        allowed_tool_prefixes=(),
        primary_outputs=("execution plan", "step rationale", "evidence expectations"),
        verification_obligations=("steps are scoped", "steps are contract-aligned"),
    ),
    "research": AgentRoleContract(
        role="research",
        summary="Collects source evidence from search and web intelligence tools.",
        allowed_tool_ids=frozenset(
            {
                "marketing.web_research",
                "marketing.competitor_profile",
                "marketing.local_discovery",
                "maps.geocode",
                "maps.distance_matrix",
                "workspace.drive.search",
                "web.extract.structured",
                "web.dataset.adapter",
            }
        ),
        allowed_tool_prefixes=("marketing.", "maps."),
        primary_outputs=("source set", "citations", "candidate findings"),
        verification_obligations=("sources are relevant", "claims are evidence-backed"),
    ),
    "browser": AgentRoleContract(
        role="browser",
        summary="Performs live browser navigation and in-page interaction.",
        allowed_tool_ids=frozenset(
            {
                "browser.playwright.inspect",
                "browser.contact_form.send",
            }
        ),
        allowed_tool_prefixes=("browser.",),
        primary_outputs=("interaction trace", "page captures", "page-state extracts"),
        verification_obligations=("actions emitted as events", "target state confirmed when possible"),
    ),
    "document": AgentRoleContract(
        role="document",
        summary="Extracts and links file-based evidence, especially from PDFs.",
        allowed_tool_ids=frozenset(
            {
                "documents.highlight.extract",
            }
        ),
        allowed_tool_prefixes=("documents.",),
        primary_outputs=("document highlights", "file-grounded evidence"),
        verification_obligations=("page/source linkage is preserved", "snippet grounding exists"),
    ),
    "analyst": AgentRoleContract(
        role="analyst",
        summary="Computes metrics, analysis artifacts, and data-driven summaries.",
        allowed_tool_ids=frozenset(
            {
                "data.dataset.analyze",
                "data.science.profile",
                "data.science.visualize",
                "data.science.ml.train",
                "data.science.deep_learning.train",
                "analytics.ga4.report",
                "ads.google.performance",
                "analytics.chart.generate",
            }
        ),
        allowed_tool_prefixes=("data.", "data.science.", "analytics.", "ads."),
        primary_outputs=("computed metrics", "tables", "charts"),
        verification_obligations=("calculation steps are reproducible", "output values are coherent"),
    ),
    "writer": AgentRoleContract(
        role="writer",
        summary="Produces user-facing report, document, and delivery content.",
        allowed_tool_ids=frozenset(
            {
                "report.generate",
                "docs.create",
                "workspace.docs.fill_template",
                "workspace.docs.research_notes",
                "workspace.sheets.track_step",
                "workspace.sheets.append",
                "email.draft",
                "gmail.draft",
                "email.send",
                "gmail.send",
                "invoice.create",
                "invoice.send",
                "slack.post_message",
                "calendar.create_event",
                "business.cloud_incident_digest_email",
                "business.invoice_workflow",
                "business.meeting_scheduler",
                "business.proposal_workflow",
                "business.ga4_kpi_sheet_report",
                "business.route_plan",
            }
        ),
        allowed_tool_prefixes=(
            "report.",
            "docs.",
            "workspace.docs.",
            "workspace.sheets.",
            "email.",
            "gmail.",
            "invoice.",
            "slack.",
            "calendar.",
            "business.",
        ),
        primary_outputs=("final report", "draft messages", "delivery artifacts"),
        verification_obligations=("recipient/target is correct", "content matches verified evidence"),
    ),
    "verifier": AgentRoleContract(
        role="verifier",
        summary="Validates coverage, readiness, and delivery truthfulness.",
        allowed_tool_ids=frozenset(
            {
                "email.validate",
            }
        ),
        allowed_tool_prefixes=(),
        primary_outputs=("verification checks", "release decision", "remediation requirements"),
        verification_obligations=("required facts covered", "completion status is truthful"),
    ),
    "safety": AgentRoleContract(
        role="safety",
        summary="Controls approvals, policy boundaries, and human-verification pauses.",
        allowed_tool_ids=frozenset(),
        allowed_tool_prefixes=(),
        primary_outputs=("approval gate decision", "pause/resume boundary"),
        verification_obligations=("high-risk actions are gated", "user consent state is explicit"),
    ),
}

_FALLBACK_ROLE_BY_TOOL_PREFIX: tuple[tuple[str, AgentRole], ...] = (
    ("browser.", "browser"),
    ("documents.", "document"),
    ("marketing.", "research"),
    ("maps.", "research"),
    ("web.extract.", "research"),
    ("web.dataset.", "research"),
    ("data.science.", "analyst"),
    ("data.", "analyst"),
    ("analytics.", "analyst"),
    ("ads.", "analyst"),
    ("workspace.docs.", "writer"),
    ("workspace.sheets.", "writer"),
    ("report.", "writer"),
    ("docs.", "writer"),
    ("email.", "writer"),
    ("gmail.", "writer"),
    ("invoice.", "writer"),
    ("slack.", "writer"),
    ("calendar.", "writer"),
    ("business.", "writer"),
)


def list_role_contracts() -> tuple[AgentRoleContract, ...]:
    return tuple(_ROLE_CONTRACTS[role] for role in list_agent_roles())


def get_role_contract(role: str | None) -> AgentRoleContract:
    normalized = normalize_agent_role(role, default=DEFAULT_AGENT_ROLE)
    return _ROLE_CONTRACTS[normalized]


def role_allows_tool(*, role: str | None, tool_id: str | None) -> bool:
    contract = get_role_contract(role)
    normalized_tool_id = " ".join(str(tool_id or "").split()).strip()
    if not normalized_tool_id:
        return False
    if normalized_tool_id in contract.allowed_tool_ids:
        return True
    lowered = normalized_tool_id.lower()
    return any(lowered.startswith(prefix) for prefix in contract.allowed_tool_prefixes)


def resolve_owner_role_for_tool(
    tool_id: str | None,
    *,
    default_role: AgentRole = "research",
) -> AgentRole:
    normalized_tool_id = " ".join(str(tool_id or "").split()).strip()
    if not normalized_tool_id:
        return default_role
    for role in list_agent_roles():
        if role_allows_tool(role=role, tool_id=normalized_tool_id):
            return role
    lowered = normalized_tool_id.lower()
    for prefix, role in _FALLBACK_ROLE_BY_TOOL_PREFIX:
        if lowered.startswith(prefix):
            return role
    return default_role

