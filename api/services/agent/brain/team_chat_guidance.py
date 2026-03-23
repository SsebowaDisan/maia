"""Prompt helpers for non-repetitive teammate-style chat."""
from __future__ import annotations

from typing import Iterable

CHAT_INTENTS: tuple[str, ...] = (
    "clarify",
    "challenge",
    "propose",
    "verify",
    "request_evidence",
    "handoff",
    "summarize",
    "flag_risk",
)


def recent_message_lines(messages: Iterable[object], *, limit: int = 6) -> list[str]:
    rows = list(messages)[-max(0, limit) :]
    normalized: list[str] = []
    for row in rows:
        speaker = getattr(row, "speaker_name", "") or getattr(row, "speaker_id", "") or "Agent"
        content = str(getattr(row, "content", "") or "").strip()
        if not content:
            continue
        normalized.append(f"{speaker}: {content[:220]}")
    return normalized


def anti_repetition_prompt(recent_lines: Iterable[str]) -> str:
    recent = [str(line).strip() for line in recent_lines if str(line).strip()]
    recent_openings = []
    for line in recent[-6:]:
        content = line.split(":", 1)[-1].strip()
        opening = " ".join(content.split()[:4]).strip()
        if opening:
            recent_openings.append(opening)
    prompt = [
        "Conversation rules:",
        "- Sound like teammates in a live work thread, not assistants reporting progress.",
        "- Do not start with a generic acknowledgement or filler. Start with the concrete move, concern, evidence, or question.",
        "- Every line must add one new thing: a check, risk, proposal, evidence request, correction, or next move.",
        f"- Pick one primary intent from: {', '.join(CHAT_INTENTS)}.",
        "- Keep it short: 1-2 sentences, under 24 words unless a longer limit is explicitly requested.",
    ]
    if recent_openings:
        prompt.append(
            f"- Avoid reusing these recent openings or sentence shapes: {', '.join(recent_openings[:6])}."
        )
    if recent:
        prompt.append("Recent thread context:")
        prompt.extend(f"  {line}" for line in recent[-6:])
    return "\n".join(prompt)
