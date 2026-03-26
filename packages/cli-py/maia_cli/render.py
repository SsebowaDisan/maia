"""Event renderers — format ACP events for terminal output."""

from __future__ import annotations

from typing import Any

from maia_cli.colors import (
    BOLD, DIM, RESET, GRAY, GREEN, RED, YELLOW,
    agent_color, badge, bold, colored, dim,
    INTENT_COLORS, ACTIVITY_ICONS, VERDICT_COLORS,
)


def _short_id(agent_id: str) -> str:
    return agent_id.replace("agent://", "")


def _time(ts: str) -> str:
    """Extract HH:MM:SS from ISO timestamp."""
    try:
        return ts[11:19] if len(ts) > 19 else ts
    except Exception:
        return ""


def render_message(event: dict[str, Any]) -> str:
    """Render a message event as a terminal line."""
    payload = event.get("payload", {})
    from_agent = payload.get("from", event.get("agent_id", "?"))
    to_agent = payload.get("to", "?")
    intent = payload.get("intent", "")
    content = payload.get("content", "")
    thinking = payload.get("thinking", "")
    mood = payload.get("mood", "")

    name = _short_id(from_agent)
    color = agent_color(from_agent)
    intent_color = INTENT_COLORS.get(intent, GRAY)
    ts = dim(_time(event.get("timestamp", "")))

    lines = []

    # Header: agent name + intent badge + timestamp
    header = f"{colored(bold(name), color)} {badge(intent, intent_color)} {ts}"
    if mood:
        header += f" {dim(mood)}"
    lines.append(header)

    # Thinking (if present)
    if thinking:
        lines.append(f"  {DIM}{YELLOW}> {thinking}{RESET}")

    # Content
    for line in content.split("\n"):
        lines.append(f"  {line}")

    return "\n".join(lines)


def render_handoff(event: dict[str, Any]) -> str:
    """Render a handoff event."""
    payload = event.get("payload", {})
    from_agent = _short_id(payload.get("from", "?"))
    to_agent = _short_id(payload.get("to", "?"))
    task = payload.get("task", {})
    desc = task.get("description", "")[:120]
    priority = task.get("priority", "normal")
    ts = dim(_time(event.get("timestamp", "")))

    color_from = agent_color(payload.get("from", ""))
    color_to = agent_color(payload.get("to", ""))

    return (
        f"{colored(bold(from_agent), color_from)} "
        f"{dim('-->')} "
        f"{colored(bold(to_agent), color_to)} "
        f"{badge('handoff', GREEN)} {ts}\n"
        f"  {desc}"
        f"{f'  [{priority}]' if priority != 'normal' else ''}"
    )


def render_review(event: dict[str, Any]) -> str:
    """Render a review event."""
    payload = event.get("payload", {})
    reviewer = _short_id(payload.get("reviewer", "?"))
    author = _short_id(payload.get("author", "?"))
    verdict = payload.get("verdict", "")
    score = payload.get("score")
    feedback = payload.get("feedback", "")
    round_num = payload.get("round", 1)
    ts = dim(_time(event.get("timestamp", "")))

    v_color = VERDICT_COLORS.get(verdict, GRAY)
    score_str = f" {dim(f'({score:.0%})')}" if score is not None else ""

    lines = [
        f"{colored(bold(reviewer), agent_color(payload.get('reviewer', '')))} "
        f"reviews {colored(bold(author), agent_color(payload.get('author', '')))} "
        f"{badge(verdict, v_color)}{score_str} "
        f"{dim(f'round {round_num}')} {ts}"
    ]
    if feedback:
        lines.append(f"  {feedback[:200]}")

    return "\n".join(lines)


def render_activity(event: dict[str, Any]) -> str:
    """Render an activity event (tool calls, browsing, etc.)."""
    payload = event.get("payload", {})
    agent_id = payload.get("agent_id", event.get("agent_id", "?"))
    name = _short_id(agent_id)
    act = payload.get("activity", "")
    detail = payload.get("detail", "")
    icon = ACTIVITY_ICONS.get(act, "\u2022")
    ts = dim(_time(event.get("timestamp", "")))
    cost = payload.get("cost")

    line = f"  {icon} {dim(name)} {act}"
    if detail:
        line += f" {dim('--')} {detail[:100]}"
    line += f" {ts}"

    if cost and isinstance(cost, dict):
        usd = cost.get("cost_usd", 0)
        tokens = cost.get("tokens_used", 0)
        if usd > 0:
            line += f" {dim(f'${usd:.4f} / {tokens} tok')}"

    return line


def render_capabilities(event: dict[str, Any]) -> str:
    """Render a capabilities event (agent joining)."""
    payload = event.get("payload", {})
    agent_id = payload.get("agent_id", "?")
    name = payload.get("name", _short_id(agent_id))
    role = payload.get("role", "")
    skills = payload.get("skills", [])
    color = agent_color(agent_id)

    skill_names = ", ".join(s.get("skill_id", "") for s in skills[:5])
    role_str = f" ({role})" if role else ""

    return (
        f"  {GREEN}+{RESET} {colored(bold(name), color)}"
        f"{dim(role_str)} joined"
        f"{f' — {dim(skill_names)}' if skill_names else ''}"
    )


def render_event(event: dict[str, Any]) -> str:
    """Route an ACP event to the correct renderer."""
    event_type = event.get("event_type", "")

    renderers = {
        "message": render_message,
        "handoff": render_handoff,
        "review": render_review,
        "event": render_activity,
        "capabilities": render_capabilities,
    }

    renderer = renderers.get(event_type)
    if renderer:
        return renderer(event)

    # Unknown event type — dump as JSON summary
    return dim(f"  [{event_type}] {str(event.get('payload', ''))[:100]}")
