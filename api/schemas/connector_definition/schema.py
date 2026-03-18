"""ConnectorDefinitionSchema — the top-level connector blueprint.

Responsibility: assemble auth + tool schemas into a validated connector definition.
A connector definition is a declarative artifact — no code, safe for marketplace
distribution. Connector instances are created via ConnectorBinding (per-tenant).
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .auth_config import AuthConfig, NoAuthConfig
from .tool_schema import ToolSchema

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}[a-z0-9]$")


class ConnectorCategory(str, Enum):
    crm = "crm"
    email = "email"
    calendar = "calendar"
    storage = "storage"
    communication = "communication"
    analytics = "analytics"
    finance = "finance"
    hr = "hr"
    developer_tools = "developer_tools"
    data = "data"
    project_management = "project_management"
    commerce = "commerce"
    support = "support"
    other = "other"


# ── Product metadata enums ────────────────────────────────────────────────

ConnectorVisibility = Literal["user_facing", "internal"]

ConnectorAuthKind = Literal[
    "oauth2", "api_key", "bearer", "basic", "service_identity", "none"
]

ConnectorSetupMode = Literal[
    "oauth_popup", "manual_credentials", "service_identity", "none"
]

ConnectorSceneFamily = Literal[
    "email", "sheet", "document", "api", "browser", "chat", "crm", "support", "commerce"
]

ConnectorSetupStatus = Literal[
    "connected", "needs_setup", "needs_permission", "expired", "invalid"
]


class ConnectorSubService(BaseModel):
    """A sub-service within a suite connector (e.g. Gmail inside Google Suite)."""

    id: str = Field(..., min_length=1, max_length=80)
    label: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=300)
    brand_slug: str = Field(default="", max_length=80)
    scene_family: ConnectorSceneFamily = "api"
    status: Literal["connected", "needs_setup", "needs_permission", "disabled"] = "needs_setup"
    required_scopes: list[str] = Field(default_factory=list)


class ConnectorDefinitionSchema(BaseModel):
    """Complete, self-contained definition for a Maia connector."""

    # ── Identity ──────────────────────────────────────────────────────────────

    # URL-safe identifier, e.g. "salesforce-crm".
    id: str = Field(..., min_length=3, max_length=64)

    # Human-readable display name.
    name: str = Field(..., min_length=1, max_length=120)

    # Short description shown in the marketplace card.
    description: str = Field(default="", max_length=500)

    # Semantic version string.
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")

    # Author / publisher label.
    author: str = Field(default="", max_length=120)

    # Marketplace category.
    category: ConnectorCategory = ConnectorCategory.other

    # Tags for marketplace search/filtering.
    tags: list[str] = Field(default_factory=list)

    # URL to the connector's logo image (shown in the marketplace).
    logo_url: str | None = None

    # Suite grouping (e.g. "google", "microsoft") — used by the frontend to
    # group related connectors under a single expandable section.
    suite_id: str | None = None
    suite_label: str | None = None

    # Display order within a suite (lower = first).
    service_order: int = 99

    # ── Product metadata ──────────────────────────────────────────────────────

    # Stable slug for brand icon resolution (e.g. "gmail", "outlook", "slack").
    brand_slug: str = Field(default="", max_length=80)

    # Whether this connector is shown to end users or is runtime-only.
    visibility: ConnectorVisibility = "user_facing"

    # Auth mechanism type for the frontend to drive setup UX.
    auth_kind: ConnectorAuthKind = "none"

    # How the setup drawer/popup should behave.
    setup_mode: ConnectorSetupMode = "none"

    # Theatre scene family — tells the frontend which visual surface to use.
    scene_family: ConnectorSceneFamily = "api"

    # Computed setup status per tenant (populated at response time, not stored).
    setup_status: ConnectorSetupStatus = "needs_setup"

    # Human-readable status message (e.g. "Token expired 2 days ago").
    setup_message: str = ""

    # Scopes required for this connector to function.
    required_scopes: list[str] = Field(default_factory=list)

    # Sub-services for suite connectors (Google, Microsoft).
    sub_services: list[ConnectorSubService] = Field(default_factory=list)

    # ── Authentication ────────────────────────────────────────────────────────

    auth: AuthConfig = Field(default_factory=NoAuthConfig)

    # ── Base URL for API calls ────────────────────────────────────────────────

    # Base URL used by the connector runtime; may contain {tenant_slug} template.
    base_url: str = ""

    # ── Tools ─────────────────────────────────────────────────────────────────

    tools: list[ToolSchema] = Field(default_factory=list)

    # ── Events (for on_event triggers) ────────────────────────────────────────

    # Event type strings this connector can emit, e.g. ["crm.lead.created"].
    emitted_event_types: list[str] = Field(default_factory=list)

    # ── Marketplace ───────────────────────────────────────────────────────────

    is_public: bool = False

    # ──────────────────────────────────────────────────────────────────────────

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _SLUG_RE.match(value):
            raise ValueError(
                "id must be lowercase alphanumeric with hyphens/underscores, "
                "3–64 characters, and start/end with alphanumeric."
            )
        return value

    def get_tool(self, tool_id: str) -> ToolSchema | None:
        """Return the tool with the given id, or None."""
        for tool in self.tools:
            if tool.id == tool_id:
                return tool
        return None

    def public_tool_ids(self) -> list[str]:
        """Return IDs of all tools marked as public."""
        return [t.id for t in self.tools if t.is_public]
