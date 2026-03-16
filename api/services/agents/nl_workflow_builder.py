"""P6-01 — Natural language → workflow YAML generator.

Responsibility: accept a free-text description of a multi-step automation and
return a validated WorkflowDefinitionSchema by calling the LLM with a
structured output prompt.

The generated workflow steps follow the same schema that workflow_executor.py
already understands, so generated YAMLs are immediately runnable.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert workflow automation designer.
Given a plain-English description of a multi-step process, output a JSON object
that strictly conforms to the WorkflowDefinitionSchema.

Schema rules:
  - Top-level keys: "name" (string), "description" (string), "steps" (array)
  - Each step has:
      step_id: unique string slug, e.g. "step_1"
      agent_id: string — the tool or agent that handles this step
      input_mapping: dict mapping input keys to prior step outputs ("step_1.result")
                     or literal values ("literal:some value")
      condition: optional string in the form "output.<key> == <value>" or similar
  - Keep steps minimal and focused on the user's intent.
  - Respond ONLY with a valid JSON object. No markdown fences, no prose.
"""


def generate_workflow(
    description: str,
    *,
    tenant_id: str,
    max_steps: int = 8,
) -> dict[str, Any]:
    """Generate a workflow definition dict from a plain-English description.

    Args:
        description: Free-text description of the automation.
        tenant_id: Used for billing/context in the underlying LLM call.
        max_steps: Soft cap on the number of steps (included in the prompt).

    Returns:
        A dict conforming to WorkflowDefinitionSchema (not yet a Pydantic model,
        so the caller can inspect/edit it before validation).

    Raises:
        ValueError: If the LLM fails to return parseable JSON.
    """
    prompt = (
        f"Description: {description.strip()}\n"
        f"Constraint: use at most {max_steps} steps.\n"
        "Output the workflow JSON:"
    )

    raw = _call_llm(tenant_id=tenant_id, system=_SYSTEM_PROMPT, user=prompt)
    return _parse_json(raw, description=description)


def validate_workflow(definition: dict[str, Any]) -> dict[str, Any]:
    """Validate a workflow dict against WorkflowDefinitionSchema.

    Returns:
        {"valid": True, "errors": []}  or
        {"valid": False, "errors": ["<message>", ...]}
    """
    from api.schemas.workflow_definition import WorkflowDefinitionSchema
    from pydantic import ValidationError

    try:
        WorkflowDefinitionSchema.model_validate(definition)
        return {"valid": True, "errors": []}
    except ValidationError as exc:
        errors = [f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return {"valid": False, "errors": errors}


# ── Private helpers ───────────────────────────────────────────────────────────

def _call_llm(*, tenant_id: str, system: str, user: str) -> str:
    """Call the existing AgentOrchestrator in ask mode and collect text output."""
    try:
        from api.services.agents.runner import run_agent_task
        parts: list[str] = []
        for chunk in run_agent_task(
            user,
            tenant_id=tenant_id,
            system_prompt=system,
            agent_mode="ask",
        ):
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                parts.append(str(text))
        return "".join(parts).strip()
    except Exception as exc:
        logger.error("NL workflow builder LLM call failed: %s", exc, exc_info=True)
        raise ValueError(f"LLM call failed: {exc}") from exc


def _parse_json(raw: str, *, description: str) -> dict[str, Any]:
    """Extract and parse the first JSON object from LLM output."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()

    # Try direct parse first
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Try to extract the outermost {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # Fallback: return a minimal skeleton so the UI can show something
    logger.warning("Could not parse LLM workflow JSON; returning skeleton. raw=%r", raw[:200])
    return {
        "name": "Generated workflow",
        "description": description,
        "steps": [],
        "_parse_error": "LLM output was not valid JSON — please edit manually.",
    }
