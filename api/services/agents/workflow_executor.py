"""B6-02 — Workflow execution engine.

Responsibility: execute a WorkflowDefinitionSchema — resolve DAG order,
run each step, pass outputs through input_mapping, evaluate edge conditions
for branching, and emit activity events throughout.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowDefinitionSchema, WorkflowEdge

logger = logging.getLogger(__name__)


class WorkflowExecutionError(Exception):
    pass


def execute_workflow(
    workflow: WorkflowDefinitionSchema,
    tenant_id: str,
    *,
    initial_inputs: dict[str, Any] | None = None,
    on_event: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """Execute a workflow and return all step outputs keyed by output_key.

    Args:
        workflow: Validated WorkflowDefinitionSchema.
        tenant_id: Active tenant.
        initial_inputs: Top-level inputs available to all step input_mappings.
        on_event: Optional callback for activity events.

    Returns:
        Dict mapping output_key → step result for every executed step.
    """
    outputs: dict[str, Any] = dict(initial_inputs or {})
    skipped_steps: set[str] = set()

    try:
        ordered_ids = workflow.topological_order()
    except ValueError as exc:
        raise WorkflowExecutionError(str(exc)) from exc

    _emit(on_event, {
        "event_type": "workflow_started",
        "workflow_id": workflow.workflow_id,
        "step_count": len(workflow.steps),
        "step_order": ordered_ids,
    })

    for step_id in ordered_ids:
        step = workflow.get_step(step_id)
        if step is None:
            continue

        # Check if all incoming edges are satisfied (skip if predecessor was skipped)
        incoming = [e for e in workflow.edges if e.to_step == step_id]
        if any(e.from_step in skipped_steps for e in incoming):
            skipped_steps.add(step_id)
            continue

        # Evaluate edge conditions from predecessors
        should_skip = False
        for edge in incoming:
            if edge.condition:
                try:
                    ok = _eval_condition(edge.condition, outputs)
                    if not ok:
                        should_skip = True
                        break
                except Exception as exc:
                    logger.warning("Edge condition eval failed: %s — skipping", exc)
                    should_skip = True
                    break

        if should_skip:
            skipped_steps.add(step_id)
            _emit(on_event, {
                "event_type": "workflow_step_skipped",
                "workflow_id": workflow.workflow_id,
                "step_id": step_id,
            })
            continue

        # Build step inputs from output_mapping
        step_inputs = _resolve_inputs(step.input_mapping, outputs)

        _emit(on_event, {
            "event_type": "workflow_step_started",
            "workflow_id": workflow.workflow_id,
            "step_id": step_id,
            "agent_id": step.agent_id,
        })

        try:
            result = _run_step(step.agent_id, step_inputs, tenant_id, on_event=on_event)
            outputs[step.output_key] = result
            _emit(on_event, {
                "event_type": "workflow_step_completed",
                "workflow_id": workflow.workflow_id,
                "step_id": step_id,
                "agent_id": step.agent_id,
                "output_key": step.output_key,
                "result_preview": str(result)[:200],
            })

        except Exception as exc:
            logger.error("Workflow step %s failed: %s", step_id, exc, exc_info=True)
            _emit(on_event, {
                "event_type": "workflow_step_failed",
                "workflow_id": workflow.workflow_id,
                "step_id": step_id,
                "error": str(exc)[:300],
            })
            raise WorkflowExecutionError(f"Step '{step_id}' failed: {exc}") from exc

    _emit(on_event, {
        "event_type": "workflow_completed",
        "workflow_id": workflow.workflow_id,
        "outputs": {k: str(v)[:200] for k, v in outputs.items()},
    })
    return outputs


# ── Private helpers ────────────────────────────────────────────────────────────

def _run_step(
    agent_id: str,
    step_inputs: dict[str, Any],
    tenant_id: str,
    on_event: Optional[Callable] = None,
) -> Any:
    from api.services.agents.definition_store import get_agent, load_schema
    from api.services.agents.runner import run_agent_task

    record = get_agent(tenant_id, agent_id)
    if not record:
        raise ValueError(f"Agent '{agent_id}' not found in tenant '{tenant_id}'.")

    schema = load_schema(record)
    task = step_inputs.get("message") or step_inputs.get("task") or (
        f"Execute your task with the following context:\n{_format_inputs(step_inputs)}"
    )

    result_parts: list[str] = []
    for chunk in run_agent_task(task, tenant_id=tenant_id, system_prompt=schema.system_prompt or None):
        text = chunk.get("text") or chunk.get("content") or ""
        if text:
            result_parts.append(str(text))
        if on_event:
            on_event({**chunk, "step_agent_id": agent_id})

    return "".join(result_parts)


def _resolve_inputs(
    input_mapping: dict[str, str],
    outputs: dict[str, Any],
) -> dict[str, Any]:
    """Resolve input_mapping entries against available outputs.

    Supports:
      - "step_key.output_key" → look up outputs["step_key.output_key"]
      - "literal:value" → use "value" directly
      - bare key → look up outputs[key]
    """
    resolved: dict[str, Any] = {}
    for param, source in input_mapping.items():
        if source.startswith("literal:"):
            resolved[param] = source[len("literal:"):]
        else:
            resolved[param] = outputs.get(source, "")
    return resolved


def _eval_condition(condition: str, outputs: dict[str, Any]) -> bool:
    """Safely evaluate a condition expression against workflow outputs."""
    safe_locals = {"output": _OutputProxy(outputs)}
    return bool(eval(condition, {"__builtins__": {}}, safe_locals))  # noqa: S307


class _OutputProxy:
    """Simple dot-access proxy over the outputs dict."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getattr__(self, key: str) -> Any:
        return self._data.get(key)


def _emit(on_event: Optional[Callable], event: dict[str, Any]) -> None:
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass


def _format_inputs(inputs: dict[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in inputs.items())
