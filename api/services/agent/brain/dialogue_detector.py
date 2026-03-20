"""Dialogue Detector — LLM-based detection of when agents should talk.

Uses an LLM call to determine if an agent's output suggests they need
input from another team member. No hardcoded patterns or keyword maps —
the LLM understands context and decides who should talk to whom.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You analyse an agent's work output to determine if they need input from a teammate.

You must respond with valid JSON only.

Response format:
{
  "needs_dialogue": true | false,
  "dialogues": [
    {
      "target_agent": "which teammate should be asked",
      "interaction_type": "short snake_case intent id",
      "interaction_label": "human-readable style for this turn",
      "scene_family": "email | sheet | document | api | browser | chat | crm | support | commerce",
      "scene_surface": "email | google_sheets | google_docs | api | website | system",
      "operation_label": "short user-facing action label",
      "question": "the specific question to ask them",
      "reason": "why this dialogue would improve the output",
      "urgency": "high" | "medium" | "low"
    }
  ]
}

Rules:
- Only flag genuine needs — missing data, unverified claims, unclear assumptions.
- Don't create dialogue just for conversation. Most outputs are fine.
- Match the question to the right teammate based on their role.
- Keep questions specific and actionable.
- You may use any interaction_type that fits the need.
- interaction_label must be readable by end users.
- scene_family and scene_surface must match the action being discussed so theatre can reflect the same action.
- operation_label should be user-facing and concrete (example: "Rewrite draft email", "Validate source evidence", "Run pricing comparison").
- Maximum 2 dialogues per output.
- If the output is complete and solid, return needs_dialogue: false with empty dialogues.
"""

_FOLLOW_UP_PROMPT = """You evaluate whether a teammate's response is sufficient.

Return strict JSON:
{
  "requires_follow_up": true | false,
  "follow_up_type": "short snake_case intent id",
  "follow_up_label": "human-readable style",
  "follow_up_prompt": "single actionable follow-up sentence",
  "reason": "why"
}

Rules:
- Only request follow-up if there is a real gap.
- If response is sufficient, requires_follow_up=false.
- Keep follow_up_prompt specific and short.
"""


def detect_dialogue_needs(
    *,
    agent_output: str,
    current_agent: str,
    available_agents: list[str],
    agent_roster: list[dict[str, Any]] | None = None,
    step_description: str = "",
    tenant_id: str = "",
) -> list[dict[str, Any]]:
    """Use LLM to detect if the agent needs to talk to a teammate.

    Returns list of dialogue needs:
      [{ target_agent, interaction_type, interaction_label, scene_family, scene_surface, operation_label, question, reason, urgency }]
    """
    if not agent_output or len(agent_output) < 100:
        return []
    if not available_agents:
        return []

    # Filter out current agent from available targets
    targets = [a for a in available_agents if a != current_agent]
    if not targets:
        return []

    roster_lines: list[str] = []
    for row in agent_roster or []:
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("agent_id", "")).strip()
        if not candidate_id or candidate_id not in targets:
            continue
        role_hint = str(row.get("step_description", "")).strip()
        if role_hint:
            roster_lines.append(f"- {candidate_id}: {role_hint[:200]}")
        else:
            roster_lines.append(f"- {candidate_id}")
    teammates_section = "\n".join(roster_lines) if roster_lines else ", ".join(targets)

    user_prompt = f"""Agent "{current_agent}" produced this output for the step: "{step_description}"

Available teammates:
{teammates_section}

Agent's output (truncated):
{agent_output[:2000]}

Does this agent need input from a teammate? Respond with JSON only."""

    try:
        from api.services.agents.runner import run_agent_task
        parts: list[str] = []
        for chunk in run_agent_task(
            user_prompt,
            tenant_id=tenant_id,
            system_prompt=_SYSTEM_PROMPT,
            max_tool_calls=0,
        ):
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                parts.append(str(text))
        raw = "".join(parts)
    except Exception as exc:
        logger.debug("Dialogue detection LLM call failed: %s", exc)
        return []

    return _parse_response(raw, targets)


def evaluate_dialogue_follow_up(
    *,
    source_agent: str,
    target_agent: str,
    interaction_type: str,
    initial_request: str,
    teammate_response: str,
    source_output: str,
    tenant_id: str = "",
) -> dict[str, Any]:
    """Use LLM to decide if the first response needs a follow-up turn."""
    if not teammate_response or len(str(teammate_response).strip()) < 20:
        return {
            "requires_follow_up": False,
            "follow_up_type": "question",
            "follow_up_label": "",
            "follow_up_prompt": "",
            "reason": "",
        }

    user_prompt = f"""Source agent: {source_agent}
Target teammate: {target_agent}
Interaction type: {interaction_type}

Initial request:
{initial_request[:1000]}

Teammate response:
{teammate_response[:2000]}

Current source output:
{source_output[:2000]}
"""

    try:
        from api.services.agents.runner import run_agent_task

        parts: list[str] = []
        for chunk in run_agent_task(
            user_prompt,
            tenant_id=tenant_id,
            system_prompt=_FOLLOW_UP_PROMPT,
            max_tool_calls=0,
        ):
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                parts.append(str(text))
        raw = "".join(parts)
    except Exception as exc:
        logger.debug("Dialogue follow-up LLM call failed: %s", exc)
        return {
            "requires_follow_up": False,
            "follow_up_type": "question",
            "follow_up_label": "",
            "follow_up_prompt": "",
            "reason": "",
        }

    parsed = _parse_json_payload(raw)
    if not isinstance(parsed, dict):
        return {
            "requires_follow_up": False,
            "follow_up_type": "question",
            "follow_up_label": "",
            "follow_up_prompt": "",
            "reason": "",
        }

    follow_up_type = _normalize_interaction_type(parsed.get("follow_up_type", "question"))
    follow_up_prompt = str(parsed.get("follow_up_prompt", "")).strip()[:500]
    requires_follow_up = bool(parsed.get("requires_follow_up")) and bool(follow_up_prompt)
    return {
        "requires_follow_up": requires_follow_up,
        "follow_up_type": follow_up_type,
        "follow_up_label": str(parsed.get("follow_up_label", "")).strip()[:120],
        "follow_up_prompt": follow_up_prompt,
        "reason": str(parsed.get("reason", "")).strip()[:300],
    }


def _parse_response(raw: str, available_agents: list[str]) -> list[dict[str, Any]]:
    """Parse the LLM response into dialogue needs."""
    parsed = _parse_json_payload(raw)
    if not isinstance(parsed, dict):
        return []

    if not isinstance(parsed, dict):
        return []
    if not parsed.get("needs_dialogue"):
        return []

    dialogues = parsed.get("dialogues", [])
    if not isinstance(dialogues, list):
        return []

    result: list[dict[str, Any]] = []
    available_lower = {a.lower(): a for a in available_agents}

    for d in dialogues[:2]:
        if not isinstance(d, dict):
            continue
        target = str(d.get("target_agent", "")).strip().lower()
        question = str(d.get("question", "")).strip()
        if not question:
            continue

        # Resolve target agent name
        resolved = available_lower.get(target)
        if not resolved:
            # Fuzzy match
            for key, name in available_lower.items():
                if target in key or key in target:
                    resolved = name
                    break
        if not resolved:
            resolved = available_agents[0]

        result.append({
            "target_agent": resolved,
            "interaction_type": _normalize_interaction_type(d.get("interaction_type", "question")),
            "interaction_label": str(d.get("interaction_label", "")).strip()[:120],
            "scene_family": _normalize_scene_family(d.get("scene_family")),
            "scene_surface": _normalize_scene_surface(d.get("scene_surface")),
            "operation_label": str(d.get("operation_label", "")).strip()[:160],
            "question": question[:500],
            "reason": str(d.get("reason", ""))[:300],
            "urgency": str(d.get("urgency", "medium")).lower(),
        })

    return result


def _normalize_interaction_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "question"
    normalized = "_".join(part for part in raw.replace("-", "_").split("_") if part)
    return normalized or "question"


def _normalize_scene_family(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    allowed = {
        "email",
        "sheet",
        "document",
        "api",
        "browser",
        "chat",
        "crm",
        "support",
        "commerce",
    }
    return normalized if normalized in allowed else ""


def _normalize_scene_surface(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    allowed = {"email", "google_sheets", "google_docs", "api", "website", "system"}
    return normalized if normalized in allowed else ""


def _parse_json_payload(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return {}

    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for i in range(len(text)):
            if text[i] != "{":
                continue
            for j in range(len(text) - 1, i, -1):
                if text[j] != "}":
                    continue
                try:
                    return json.loads(text[i:j + 1])
                except json.JSONDecodeError:
                    continue
        return {}
