"""TriggerConfig — defines when and how an agent activates.

Responsibility: single pydantic schema for agent trigger configuration.
Three trigger families: conversational, scheduled, on_event (webhook).
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class TriggerFamily(str, Enum):
    conversational = "conversational"
    scheduled = "scheduled"
    on_event = "on_event"


class ConversationalTrigger(BaseModel):
    """Agent is invoked when a user message matches routing rules."""

    family: Literal[TriggerFamily.conversational] = TriggerFamily.conversational

    # Keywords/phrases that route the message to this agent (case-insensitive).
    keywords: list[str] = Field(default_factory=list)

    # Regex patterns applied to user message before routing.
    patterns: list[str] = Field(default_factory=list)

    # If True, this agent handles all messages not matched by more specific agents.
    is_default_fallback: bool = False

    # Minimum confidence threshold from the router classifier (0–1).
    min_router_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0


class ScheduledTrigger(BaseModel):
    """Agent is invoked on a cron schedule."""

    family: Literal[TriggerFamily.scheduled] = TriggerFamily.scheduled

    # Standard cron expression: "0 9 * * 1" = every Monday at 09:00.
    cron_expression: str

    # IANA timezone for cron evaluation.
    timezone: str = "UTC"

    # Maximum seconds to wait before giving up on an invocation.
    timeout_seconds: Annotated[int, Field(ge=30, le=86400)] = 3600

    # Static payload passed to the agent as initial context.
    payload: dict = Field(default_factory=dict)


class OnEventTrigger(BaseModel):
    """Agent is invoked when an external webhook/event fires."""

    family: Literal[TriggerFamily.on_event] = TriggerFamily.on_event

    # Logical event type string, e.g. "crm.lead.created".
    event_type: str

    # Which connector emits this event.
    source_connector_id: str

    # JSONPath filter applied to the event payload — agent only runs if truthy.
    filter_expression: str | None = None

    # Maximum seconds to wait for the agent to complete after event receipt.
    timeout_seconds: Annotated[int, Field(ge=5, le=3600)] = 300


TriggerConfig = Annotated[
    Union[ConversationalTrigger, ScheduledTrigger, OnEventTrigger],
    Field(discriminator="family"),
]
