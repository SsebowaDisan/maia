"""GateConfig — human-in-the-loop checkpoints for agent tool calls.

Responsibility: single pydantic schema for gate (approval) configuration.
The gate engine intercepts matching tool calls, pauses execution, emits a
gate_pending event, and waits for human approve/reject before continuing.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class GateFallbackAction(str, Enum):
    """What happens when the gate times out with no human response."""

    skip = "skip"        # Skip the tool call, return empty result.
    abort = "abort"      # Abort the agent run with an error.
    auto_approve = "auto_approve"  # Approve automatically (use with care).


class GateConfig(BaseModel):
    """Single gate rule — intercepts a specific tool and requires approval.

    Multiple gate configs are collected in AgentDefinitionSchema.gates list.
    """

    # Logical name shown to the reviewer, e.g. "Send email gate".
    name: str

    # Tool IDs this gate applies to (exact match against tool_id in the call).
    # Use ["*"] to gate every tool call made by this agent.
    tool_ids: list[str] = Field(default_factory=list)

    # Human-readable instructions shown in the approval UI.
    approval_prompt: str = "Please review this action before it is executed."

    # Seconds to wait for a human response before applying fallback_action.
    timeout_seconds: Annotated[int, Field(ge=10, le=86400)] = 3600

    # What to do when timeout is reached with no decision.
    fallback_action: GateFallbackAction = GateFallbackAction.skip

    # If True, approval is remembered per session (same tool+args within the
    # same run will not prompt again).
    remember_approval_in_session: bool = False

    # Notification channels to alert reviewers (e.g. ["email", "slack"]).
    notify_channels: list[str] = Field(default_factory=list)
