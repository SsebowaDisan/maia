"""OutputConfig — controls what block types an agent may emit.

Responsibility: single pydantic schema for agent output configuration.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AllowedBlockType(str, Enum):
    """Block types that an agent is permitted to include in its response."""

    markdown = "markdown"
    code = "code"
    math = "math"
    widget = "widget"
    canvas_document = "canvas_document"
    table = "table"
    image = "image"
    chart = "chart"
    citation = "citation"
    error = "error"


class OutputFormat(str, Enum):
    """Top-level format of the agent's final answer."""

    chat = "chat"           # Standard conversational reply.
    report = "report"       # Long-form structured report.
    email = "email"         # Email draft (subject + body).
    json = "json"           # Machine-readable JSON payload.
    table = "table"         # Tabular data response.


class OutputConfig(BaseModel):
    """Constraints on what an agent is allowed to output."""

    format: OutputFormat = OutputFormat.chat

    # Subset of block types this agent may emit. Empty list = all allowed.
    allowed_block_types: list[AllowedBlockType] = Field(default_factory=list)

    # If True, the agent will stream partial results as they are generated.
    stream: bool = True

    # Maximum tokens for the final answer (None = no limit beyond model max).
    max_tokens: int | None = None

    # Language code for the response, e.g. "en", "fr". None = auto-detect.
    language: str | None = None

    # If True, the agent appends recommended next steps at the end.
    include_next_steps: bool = True

    # If True, the agent includes source citations.
    include_citations: bool = True
