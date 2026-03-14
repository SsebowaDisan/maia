"""ConnectorDefinitionSchema — the top-level connector blueprint.

Responsibility: assemble auth + tool schemas into a validated connector definition.
A connector definition is a declarative artifact — no code, safe for marketplace
distribution. Connector instances are created via ConnectorBinding (per-tenant).
"""
from __future__ import annotations

import re
from enum import Enum

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
    other = "other"


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
