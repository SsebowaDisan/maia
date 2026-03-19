"""Handoff Manager — smooth agent-to-agent transitions during workflow runs.

When one agent finishes and hands off to the next, this service:
1. Summarizes what the previous agent did
2. Formats context for the next agent
3. Emits a transition event for the frontend to animate
4. Tracks the handoff chain for debugging

This makes multi-agent workflows feel like a team conversation,
not a sequence of disconnected steps.
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class HandoffContext:
    """Context passed between agents during a handoff."""

    def __init__(
        self,
        *,
        from_agent: str,
        to_agent: str,
        from_step_id: str = "",
        to_step_id: str = "",
        summary: str = "",
        key_findings: list[str] | None = None,
        output_preview: str = "",
        handoff_instruction: str = "",
    ):
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.from_step_id = from_step_id
        self.to_step_id = to_step_id
        self.summary = summary
        self.key_findings = key_findings or []
        self.output_preview = output_preview
        self.handoff_instruction = handoff_instruction
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "from_step_id": self.from_step_id,
            "to_step_id": self.to_step_id,
            "summary": self.summary,
            "key_findings": self.key_findings,
            "output_preview": self.output_preview,
            "handoff_instruction": self.handoff_instruction,
            "timestamp": self.timestamp,
        }

    def to_prompt_context(self) -> str:
        """Format as text to inject into the next agent's prompt."""
        lines = [f"The {self.from_agent} agent has completed their work and handed off to you."]
        if self.summary:
            lines.append(f"\nSummary of their findings:\n{self.summary}")
        if self.key_findings:
            lines.append("\nKey findings:")
            for finding in self.key_findings[:10]:
                lines.append(f"  • {finding}")
        if self.handoff_instruction:
            lines.append(f"\nYour task: {self.handoff_instruction}")
        return "\n".join(lines)


def build_handoff_context(
    *,
    from_agent: str,
    to_agent: str,
    from_step_id: str = "",
    to_step_id: str = "",
    previous_output: str = "",
    step_description: str = "",
    run_id: str = "",
) -> HandoffContext:
    """Build handoff context from the previous step's output."""
    summary = _summarize_output(previous_output)
    key_findings = _extract_key_findings(previous_output)
    preview = previous_output[:500] if previous_output else ""

    context = HandoffContext(
        from_agent=from_agent,
        to_agent=to_agent,
        from_step_id=from_step_id,
        to_step_id=to_step_id,
        summary=summary,
        key_findings=key_findings,
        output_preview=preview,
        handoff_instruction=step_description,
    )

    # Emit transition event for frontend animation
    _emit_handoff_event(run_id, context)

    # Record in collaboration log
    try:
        from api.services.agent.collaboration_logs import get_collaboration_service
        get_collaboration_service().record_handoff(
            run_id=run_id,
            from_agent=from_agent,
            to_agent=to_agent,
            task=step_description or f"Handoff from {from_agent} to {to_agent}",
            context=summary,
        )
    except Exception:
        pass

    return context


def _summarize_output(output: str) -> str:
    """Quick extractive summary — take first 2 sentences or 200 chars."""
    if not output:
        return ""
    text = output.strip()[:1000]
    sentences = [s.strip() for s in text.replace("\n", ". ").split(". ") if s.strip()]
    if len(sentences) <= 2:
        return text[:300]
    return ". ".join(sentences[:2]) + "."


def _extract_key_findings(output: str) -> list[str]:
    """Extract bullet points or numbered items from output."""
    findings: list[str] = []
    for line in output.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("- ", "• ", "* ", "1.", "2.", "3.", "4.", "5.")):
            clean = stripped.lstrip("-•* 0123456789.").strip()
            if clean and len(clean) > 10:
                findings.append(clean[:200])
            if len(findings) >= 5:
                break
    return findings


def _emit_handoff_event(run_id: str, context: HandoffContext) -> None:
    """Emit a live event for the frontend to show a smooth transition."""
    try:
        from api.services.agent.live_events import get_live_event_broker
        get_live_event_broker().publish(
            user_id="",
            run_id=run_id,
            event={
                "event_type": "agent_handoff",
                "title": f"{context.from_agent} → {context.to_agent}",
                "detail": context.summary[:200],
                "stage": "execute",
                "status": "info",
                "data": {
                    **context.to_dict(),
                    "event_family": "plan",
                    "scene_family": "api",
                },
            },
        )
    except Exception:
        pass
