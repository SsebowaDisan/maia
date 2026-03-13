"""Brain signal contracts.

Typed, immutable data structures that flow between the execution layer and
the Brain.  No logic here — only data shapes.

StepOutcome  — what happened when a tool ran
BrainSignal  — message emitted by a role/tool to the Brain
BrainDirective — what the Brain tells the executor to do next
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

StepOutcomeStatus = Literal[
    "success",   # tool ran and returned useful content
    "empty",     # tool ran but returned nothing meaningful
    "failed",    # tool raised an exception
    "blocked",   # tool hit a barrier (auth wall, CAPTCHA)
    "skipped",   # executor decided not to run this step
]

DirectiveAction = Literal[
    "continue",         # proceed with next planned step as-is
    "add_steps",        # inject new steps at the END of remaining queue
    "halt",             # stop; use best-available answer
    "pause_for_handoff",# suspend and wait for human
]


@dataclass(frozen=True)
class StepOutcome:
    """Captured result of one tool execution."""
    step_index: int
    tool_id: str
    owner_role: str
    status: StepOutcomeStatus
    # Content summary from the tool result (used by coverage + reviser LLMs).
    content_summary: str
    # How many source objects / evidence rows the tool produced.
    evidence_count: int
    # Non-empty only when status == "failed".
    error_message: str
    duration_ms: int
    # Tool-specific extra (urls found, rows written, etc.)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = field(default_factory=lambda: int(time.monotonic() * 1000))


@dataclass(frozen=True)
class BrainSignal:
    """Emitted by a role after a step, carrying outcome to the Brain."""
    source_role: str
    outcome: StepOutcome
    # Optional: role explicitly identifies a gap (e.g. "found no deals > 30 days")
    gap_note: str = ""
    timestamp_ms: int = field(default_factory=lambda: int(time.monotonic() * 1000))


@dataclass(frozen=True)
class BrainDirective:
    """Returned by Brain.assess() — tells the executor what to do next."""
    action: DirectiveAction
    # Populated when action == "add_steps".
    injected_steps: list[dict[str, Any]] = field(default_factory=list)
    # Populated when action == "halt".
    halt_reason: str | None = None
    # Human-readable explanation logged and emitted as a brain event.
    directive_reason: str = ""
    # The Brain's own rationale text (shown to user as a "thinking" message).
    brain_thought: str = ""
