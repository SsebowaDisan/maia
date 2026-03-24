from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Optional

from api.services.agent.brain.team_role_catalog import format_role_catalog_for_prompt

logger = logging.getLogger(__name__)
_ROLE_CATALOG_PROMPT = format_role_catalog_for_prompt()
_SYSTEM_PROMPT = """You are a workflow architect. Given a task description, decompose it into a team of agents that collaborate.

Respond with valid JSON only:
{
  "steps": [
    {
      "step_id": "step_1",
      "agent_role": "freeform role label that best fits the task",
      "description": "what this step does",
      "tools_needed": ["tool.id"] or []
    }
  ],
  "edges": [
    { "from_step": "step_1", "to_step": "step_2" }
  ],
  "connectors_needed": [
    { "connector_id": "gmail", "reason": "to send the email report" }
  ]
}

Rules:
- Define roles from the request context; do not force generic role templates.
- Choose from the role catalog when it helps the task, but only include roles that have real work to do.
- For multi-step work, include supervision or review roles when they add decision value.
- Use browser, document, email, delivery, or reviewer roles when the request explicitly needs those surfaces.
- Preserve the user's scope exactly. Do not inject arbitrary time windows, source types, or academic-only constraints unless the user explicitly asks for them.
- For a general 'research about X' request, prefer a balanced overview using authoritative representative sources rather than a latest-papers sweep.
- Only bias toward recent papers, last-30-days coverage, or narrow benchmark scans when the user explicitly asks for recency, papers, or benchmarks.
- If the user asks for an email deliverable, ensure one step synthesizes cited findings into delivery-ready writing and one step handles delivery.
- Keep it minimal — do not add steps that are not required by the request.
- Do not default to generic role chains (for example researcher→analyst→writer→deliverer) unless the request truly needs them.
- Use one step when one step is enough.
- Connect steps based on dependency logic, not fixed phase assumptions.
- Identify which connectors (gmail, google_analytics, slack, etc.) are needed.
- If the user provides a concrete recipient/target, preserve it in the relevant delivery step description.
- If the request says not to browse/search, do not add browser/search connectors or steps.
- Maximum 6 steps.
- step_id format: step_1, step_2, etc.

Role catalog:
__ROLE_CATALOG__""".replace("__ROLE_CATALOG__", _ROLE_CATALOG_PROMPT)
_RESERVED_ORCHESTRATOR_ROLES = {
    "brain",
    "maia brain",
    "maia_brain",
    "workflow architect",
    "workflow planner",
    "orchestrator",
}


def _normalize_role_key(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _extract_email(text: str) -> str:
    match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", str(text or ""))
    return str(match.group(1)).strip().rstrip(".,;:!?") if match else ""


def _parse_plan(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "steps" in parsed:
            return parsed
    except json.JSONDecodeError:
        pass
    for i in range(len(text)):
        if text[i] == "{":
            for j in range(len(text) - 1, i, -1):
                if text[j] == "}":
                    try:
                        parsed = json.loads(text[i:j + 1])
                        if isinstance(parsed, dict) and "steps" in parsed:
                            return parsed
                    except json.JSONDecodeError:
                        continue
    return {"steps": [], "edges": [], "connectors_needed": []}


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    for i in range(len(text)):
        if text[i] != "{":
            continue
        for j in range(len(text) - 1, i, -1):
            if text[j] != "}":
                continue
            try:
                parsed = json.loads(text[i : j + 1])
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                continue
    return None


def _planner_runtime_available() -> tuple[bool, str]:
    try:
        from api.services.agent.llm_runtime import has_openai_credentials
        if has_openai_credentials():
            return True, "openai"
    except Exception:
        pass
    try:
        if bool(str(os.getenv("ANTHROPIC_API_KEY", "")).strip()):
            return True, "anthropic"
    except Exception:
        pass
    return False, "none"


def _assembly_timeout_seconds() -> float:
    raw = str(os.getenv("MAIA_ASSEMBLY_LLM_TIMEOUT_SEC", "25")).strip()
    try:
        parsed = float(raw)
    except Exception:
        return 25.0
    return max(5.0, min(parsed, 120.0))


def _fallback_intent_timeout_seconds() -> float:
    raw = str(os.getenv("MAIA_FALLBACK_INTENT_TIMEOUT_SEC", "8")).strip()
    try:
        parsed = float(raw)
    except Exception:
        return 8.0
    return max(3.0, min(parsed, 30.0))


def _emit(on_event: Optional[Callable], run_id: str, event: dict[str, Any]) -> None:
    event.setdefault("status", "info")
    event.setdefault("data", {})
    event["data"]["run_id"] = run_id
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass
    try:
        from api.services.agent.live_events import get_live_event_broker
        get_live_event_broker().publish(user_id="", run_id=run_id, event=event)
    except Exception:
        pass
