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

_SEED_DIALOGUE_PROMPT = """You create one high-value teammate check-in message for a live team workflow.

Return strict JSON:
{
  "target_agent": "teammate agent id",
  "interaction_type": "short snake_case intent id",
  "interaction_label": "human-readable style",
  "scene_family": "email | sheet | document | api | browser | chat | crm | support | commerce",
  "scene_surface": "email | google_sheets | google_docs | api | website | system",
  "operation_label": "short user-facing action label",
  "question": "single actionable teammate message",
  "reason": "why this helps confidence/quality"
}

Rules:
- Produce exactly one useful peer-review turn.
- Keep it short, concrete, and tied to the current step output.
- Do not invent unavailable agents.
"""

_SCENE_CLASSIFIER_PROMPT = """Classify the correct theatre scene metadata for this teammate interaction.

Return strict JSON:
{
  "scene_family": "email | sheet | document | api | browser | chat | crm | support | commerce",
  "scene_surface": "email | google_sheets | google_docs | api | website | system"
}

Rules:
- Choose values that best match the action being discussed.
- Do not add extra keys.
- Return JSON only.
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
    if not agent_output or len(agent_output) < 40:
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

    payload = _call_json_with_fallback(
        tenant_id=tenant_id,
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        timeout_seconds=18,
        max_tokens=700,
    )
    if not isinstance(payload, dict):
        logger.debug("Dialogue detection LLM call failed")
        return []

    return _parse_response(payload, targets)


def propose_seed_dialogue_turn(
    *,
    agent_output: str,
    current_agent: str,
    available_agents: list[str],
    agent_roster: list[dict[str, Any]] | None = None,
    step_description: str = "",
    tenant_id: str = "",
) -> dict[str, Any]:
    """Use LLM to propose one teammate check-in when no dialogue was found."""
    if not available_agents:
        return {}
    targets = [a for a in available_agents if a != current_agent]
    if not targets:
        return {}

    roster_lines: list[str] = []
    for row in agent_roster or []:
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("agent_id", "")).strip()
        if not candidate_id or candidate_id not in targets:
            continue
        role_hint = str(row.get("step_description", "")).strip()
        roster_lines.append(f"- {candidate_id}: {role_hint[:200] if role_hint else 'teammate'}")
    teammates_section = "\n".join(roster_lines) if roster_lines else ", ".join(targets)

    user_prompt = f"""Current agent: {current_agent}
Current step: {step_description}

Available teammates:
{teammates_section}

Current output draft:
{agent_output[:2000]}
"""

    parsed = _call_json_with_fallback(
        tenant_id=tenant_id,
        system_prompt=_SEED_DIALOGUE_PROMPT,
        user_prompt=user_prompt,
        timeout_seconds=16,
        max_tokens=520,
    )
    if not isinstance(parsed, dict):
        logger.debug("Seed dialogue LLM call failed")
        return {}
    target = str(parsed.get("target_agent", "")).strip().lower()
    resolved = ""
    targets_lower = {t.lower(): t for t in targets}
    if target:
        resolved = targets_lower.get(target, "")
        if not resolved:
            for key, value in targets_lower.items():
                if target in key or key in target:
                    resolved = value
                    break
    if not resolved:
        resolved = targets[0]

    question = str(parsed.get("question", "")).strip()
    if not question:
        return {}

    return {
        "target_agent": resolved,
        "interaction_type": _normalize_interaction_type(parsed.get("interaction_type", "peer_review_request")),
        "interaction_label": str(parsed.get("interaction_label", "")).strip()[:120],
        "scene_family": _normalize_scene_family(parsed.get("scene_family")),
        "scene_surface": _normalize_scene_surface(parsed.get("scene_surface")),
        "operation_label": str(parsed.get("operation_label", "")).strip()[:160],
        "question": question[:500],
        "reason": str(parsed.get("reason", "")).strip()[:300],
        "urgency": "low",
    }


def infer_dialogue_scene(
    *,
    current_agent: str,
    target_agent: str,
    interaction_type: str,
    interaction_label: str,
    operation_label: str,
    question: str,
    reason: str,
    step_description: str,
    source_output: str,
    tenant_id: str = "",
) -> dict[str, str]:
    """Infer scene metadata for dialogue turns when planners omit it."""
    if not tenant_id:
        return {}

    user_prompt = f"""Current agent: {current_agent}
Target teammate: {target_agent}
Interaction type: {interaction_type}
Interaction label: {interaction_label}
Operation label: {operation_label}
Step description: {step_description}
Question/request:
{question[:600]}

Reason:
{reason[:300]}

Source output excerpt:
{source_output[:1000]}
"""

    parsed = _call_json_with_fallback(
        tenant_id=tenant_id,
        system_prompt=_SCENE_CLASSIFIER_PROMPT,
        user_prompt=user_prompt,
        timeout_seconds=12,
        max_tokens=180,
    )
    if not isinstance(parsed, dict):
        logger.debug("Dialogue scene inference LLM call failed")
        return {}
    return {
        "scene_family": _normalize_scene_family(parsed.get("scene_family")),
        "scene_surface": _normalize_scene_surface(parsed.get("scene_surface")),
    }


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

    parsed = _call_json_with_fallback(
        tenant_id=tenant_id,
        system_prompt=_FOLLOW_UP_PROMPT,
        user_prompt=user_prompt,
        timeout_seconds=14,
        max_tokens=360,
    )
    if not isinstance(parsed, dict):
        logger.debug("Dialogue follow-up LLM call failed")
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


def _parse_response(parsed: dict[str, Any], available_agents: list[str]) -> list[dict[str, Any]]:
    """Parse the LLM response into dialogue needs."""
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


def _call_json_with_fallback(
    *,
    tenant_id: str,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: int,
    max_tokens: int,
) -> dict[str, Any] | None:
    try:
        from api.services.agent.llm_runtime import call_json_response

        payload = call_json_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=max(8, int(timeout_seconds)),
            max_tokens=max_tokens,
            retries=1,
            allow_json_repair=True,
            enable_thinking=False,
            use_fallback_models=False,
        )
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    try:
        import concurrent.futures
        from api.services.agents.runner import run_agent_task

        def _run() -> dict[str, Any] | None:
            parts: list[str] = []
            for chunk in run_agent_task(
                user_prompt,
                tenant_id=tenant_id,
                system_prompt=system_prompt,
                agent_mode="ask",
                max_tool_calls=0,
            ):
                text = chunk.get("text") or chunk.get("content") or ""
                if text:
                    parts.append(str(text))
            raw = "".join(parts)
            parsed = _parse_json_payload(raw)
            return parsed if isinstance(parsed, dict) else None

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(_run)
        try:
            return future.result(timeout=max(8, int(timeout_seconds)))
        except concurrent.futures.TimeoutError:
            future.cancel()
            return None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        return None


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
