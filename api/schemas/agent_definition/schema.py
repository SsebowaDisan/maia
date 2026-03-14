"""AgentDefinitionSchema — the top-level agent configuration contract.

Responsibility: assemble all sub-configs into a single validated definition.
An agent definition is a declarative YAML/JSON artifact — no code, safe for
marketplace distribution and multi-tenant loading.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from .gate_config import GateConfig
from .memory_config import MemoryConfig
from .output_config import OutputConfig
from .trigger_config import (
    ConversationalTrigger,
    OnEventTrigger,
    ScheduledTrigger,
    TriggerConfig,
)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}[a-z0-9]$")


class AgentDefinitionSchema(BaseModel):
    """Complete, self-contained definition for a Maia agent."""

    # ── Identity ──────────────────────────────────────────────────────────────

    # URL-safe identifier, e.g. "lead-enrichment-agent".
    id: str = Field(..., min_length=3, max_length=64)

    # Human-readable display name.
    name: str = Field(..., min_length=1, max_length=120)

    # Short description shown in the marketplace card.
    description: str = Field(default="", max_length=500)

    # Semantic version string, e.g. "1.0.0".
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")

    # Author / publisher label shown in the marketplace.
    author: str = Field(default="", max_length=120)

    # Tags for marketplace search/filtering.
    tags: list[str] = Field(default_factory=list)

    # ── Behaviour ─────────────────────────────────────────────────────────────

    # System prompt injected before every conversation turn.
    system_prompt: str = Field(default="", max_length=32000)

    # Tool IDs the agent is allowed to call (must exist in its connector bindings).
    tools: list[str] = Field(default_factory=list)

    # Maximum depth for sub-agent delegation chains (prevents infinite loops).
    max_delegation_depth: Annotated[int, Field(ge=0, le=10)] = 0

    # IDs of agents this agent is permitted to delegate to.
    allowed_sub_agent_ids: list[str] = Field(default_factory=list)

    # ── Sub-configs ───────────────────────────────────────────────────────────

    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    # At most one trigger per agent (multi-trigger routing is handled by the
    # platform router, not within a single definition).
    trigger: TriggerConfig | None = None

    # Gate rules — each rule can cover multiple tool_ids.
    gates: list[GateConfig] = Field(default_factory=list)

    # ── Marketplace metadata ──────────────────────────────────────────────────

    # Whether this definition is listed in the public marketplace.
    is_public: bool = False

    # Billing model: "free" | "per_use" | "subscription".
    pricing_model: str = "free"

    # Price in USD cents per invocation (only relevant for per_use).
    price_per_use_cents: int = 0

    # ── Timestamps (set by the platform, not the author) ─────────────────────

    date_created: datetime | None = None
    date_updated: datetime | None = None

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

    @model_validator(mode="after")
    def _validate_delegation(self) -> "AgentDefinitionSchema":
        if self.max_delegation_depth > 0 and not self.allowed_sub_agent_ids:
            raise ValueError(
                "allowed_sub_agent_ids must list at least one sub-agent when "
                "max_delegation_depth > 0."
            )
        return self

    def gated_tool_ids(self) -> set[str]:
        """Return the set of tool IDs that have at least one gate rule."""
        result: set[str] = set()
        for gate in self.gates:
            if gate.tool_ids == ["*"]:
                # All tools are gated — return the full tools list.
                return set(self.tools)
            result.update(gate.tool_ids)
        return result
