"""B6-02 — Workflow execution engine.

Responsibility: execute a WorkflowDefinitionSchema — resolve DAG order,
run independent steps in parallel (B8), pass outputs through input_mapping,
validate step outputs against output_schema (B6), maintain a shared run
context (B7), evaluate edge conditions for branching, and emit activity events.

Changes since original:
  B6  — output_schema validation via jsonschema (optional dep, falls back to warn)
  B7  — WorkflowRunContext integrated; context.* keys available in input_mapping
  B8  — Independent steps grouped into parallel batches (ThreadPoolExecutor)
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as _FuturesTimeout
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowDefinitionSchema, WorkflowEdge, WorkflowStep

logger = logging.getLogger(__name__)

_MAX_PARALLEL_STEPS = 5   # cap concurrent step threads
_RETRY_BASE_DELAY = 1.0   # seconds — exponential backoff base


class WorkflowExecutionError(Exception):
    pass


def execute_workflow(
    workflow: WorkflowDefinitionSchema,
    tenant_id: str,
    *,
    initial_inputs: dict[str, Any] | None = None,
    on_event: Optional[Callable[[dict[str, Any]], None]] = None,
    run_id: str | None = None,
    step_timeout_s: int = 300,
) -> dict[str, Any]:
    """Execute a workflow and return all step outputs keyed by output_key.

    Args:
        workflow: Validated WorkflowDefinitionSchema.
        tenant_id: Active tenant.
        initial_inputs: Top-level inputs available to all step input_mappings.
        on_event: Optional callback for activity events.
        run_id: Optional run ID used to key the shared WorkflowRunContext (B7).

    Returns:
        Dict mapping output_key → step result for every executed step.
    """
    from api.services.agents.workflow_context import WorkflowRunContext, cleanup_context

    effective_run_id = run_id or str(uuid.uuid4())
    ctx = WorkflowRunContext(effective_run_id)
    outputs: dict[str, Any] = dict(initial_inputs or {})
    outputs_lock = threading.Lock()
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
        "run_id": effective_run_id,
    })

    # B8: Group steps into parallel execution batches.
    batches = _build_parallel_batches(workflow, ordered_ids)

    for batch in batches:
        runnable: list[str] = []
        for step_id in batch:
            step = workflow.get_step(step_id)
            if step is None:
                continue
            incoming = [e for e in workflow.edges if e.to_step == step_id]
            if any(e.from_step in skipped_steps for e in incoming):
                skipped_steps.add(step_id)
                _emit(on_event, {
                    "event_type": "workflow_step_skipped",
                    "workflow_id": workflow.workflow_id,
                    "step_id": step_id,
                    "reason": "predecessor_skipped",
                })
                continue
            if _check_conditions(incoming, outputs, on_event, workflow, step_id):
                skipped_steps.add(step_id)
            else:
                runnable.append(step_id)

        if not runnable:
            continue

        if len(runnable) == 1:
            _execute_step(workflow, runnable[0], outputs, outputs_lock, ctx, tenant_id, on_event, skipped_steps, step_timeout_s, effective_run_id)
        else:
            # B8: Run independent steps concurrently
            _execute_batch(workflow, runnable, outputs, outputs_lock, ctx, tenant_id, on_event, skipped_steps, step_timeout_s, effective_run_id)

    _emit(on_event, {
        "event_type": "workflow_completed",
        "workflow_id": workflow.workflow_id,
        "run_id": effective_run_id,
        "outputs": {k: str(v)[:200] for k, v in outputs.items()},
    })

    cleanup_context(effective_run_id)
    return outputs


# ── Parallel batch builder (B8) ────────────────────────────────────────────────

def _build_parallel_batches(
    workflow: WorkflowDefinitionSchema,
    ordered_ids: list[str],
) -> list[list[str]]:
    """Group the topological order into parallel execution batches."""
    deps: dict[str, set[str]] = {s.step_id: set() for s in workflow.steps}
    for edge in workflow.edges:
        deps[edge.to_step].add(edge.from_step)

    batches: list[list[str]] = []
    completed: set[str] = set()
    remaining = list(ordered_ids)

    while remaining:
        batch = [sid for sid in remaining if deps[sid].issubset(completed)]
        if not batch:
            batch = [remaining[0]]  # Fallback — avoids infinite loop
        batches.append(batch)
        for sid in batch:
            remaining.remove(sid)
            completed.add(sid)

    return batches


# ── Step execution helpers ─────────────────────────────────────────────────────

def _execute_batch(
    workflow: WorkflowDefinitionSchema,
    step_ids: list[str],
    outputs: dict[str, Any],
    outputs_lock: threading.Lock,
    ctx: Any,
    tenant_id: str,
    on_event: Optional[Callable],
    skipped_steps: set[str],
    step_timeout_s: int = 300,
    run_id: str = "",
) -> None:
    cap = min(len(step_ids), _MAX_PARALLEL_STEPS)
    futures = {}

    # Compute per-step timeouts; use max for as_completed batch-level timeout
    step_timeouts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=cap, thread_name_prefix="wf-step") as pool:
        for step_id in step_ids:
            step = workflow.get_step(step_id)
            if step is None:
                continue
            with outputs_lock:
                step_inputs = _resolve_inputs(step.input_mapping, outputs, ctx)
            _emit(on_event, {
                "event_type": "workflow_step_started",
                "workflow_id": workflow.workflow_id,
                "step_id": step_id,
                "agent_id": step.agent_id,
                "step_type": step.step_type,
                "parallel": True,
            })
            timeout = step.timeout_s or step_timeout_s
            step_timeouts[step.step_id] = timeout
            futures[pool.submit(
                _run_step_with_retry, step, step_inputs, tenant_id,
                workflow.workflow_id, run_id, on_event,
            )] = (step, timeout)

        # Batch-level timeout = max of all individual step timeouts + buffer
        batch_timeout = max(step_timeouts.values(), default=step_timeout_s) + 10

        for future in as_completed(futures, timeout=batch_timeout):
            step, timeout = futures[future]
            try:
                result = future.result(timeout=timeout)
                _validate_output(step, result, workflow.workflow_id, on_event)
                with outputs_lock:
                    outputs[step.output_key] = result
                _emit(on_event, {
                    "event_type": "workflow_step_completed",
                    "workflow_id": workflow.workflow_id,
                    "step_id": step.step_id,
                    "agent_id": step.agent_id,
                    "output_key": step.output_key,
                    "result_preview": str(result)[:2000],
                })
            except _FuturesTimeout as exc:
                logger.error("Workflow step %s timed out", step.step_id)
                _emit(on_event, {
                    "event_type": "workflow_step_failed",
                    "workflow_id": workflow.workflow_id,
                    "step_id": step.step_id,
                    "error": f"Step timed out after {timeout}s",
                })
                raise WorkflowExecutionError(f"Step '{step.step_id}' timed out after {timeout}s") from exc
            except Exception as exc:
                logger.error("Workflow step %s failed: %s", step.step_id, exc, exc_info=True)
                _emit(on_event, {
                    "event_type": "workflow_step_failed",
                    "workflow_id": workflow.workflow_id,
                    "step_id": step.step_id,
                    "error": str(exc)[:2000],
                })
                raise WorkflowExecutionError(f"Step '{step.step_id}' failed: {exc}") from exc


def _execute_step(
    workflow: WorkflowDefinitionSchema,
    step_id: str,
    outputs: dict[str, Any],
    outputs_lock: threading.Lock,
    ctx: Any,
    tenant_id: str,
    on_event: Optional[Callable],
    skipped_steps: set[str],
    step_timeout_s: int = 300,
    run_id: str = "",
) -> None:
    step = workflow.get_step(step_id)
    if step is None:
        return
    with outputs_lock:
        step_inputs = _resolve_inputs(step.input_mapping, outputs, ctx)
    timeout = step.timeout_s or step_timeout_s
    _emit(on_event, {
        "event_type": "workflow_step_started",
        "workflow_id": workflow.workflow_id,
        "step_id": step_id,
        "agent_id": step.agent_id,
        "step_type": step.step_type,
        "parallel": False,
    })
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="wf-step-to") as _pool:
            _fut = _pool.submit(
                _run_step_with_retry, step, step_inputs, tenant_id,
                workflow.workflow_id, run_id, on_event,
            )
            try:
                result = _fut.result(timeout=timeout)
            except _FuturesTimeout as te:
                raise TimeoutError(f"Step '{step_id}' timed out after {timeout}s") from te
        _validate_output(step, result, workflow.workflow_id, on_event)
        with outputs_lock:
            outputs[step.output_key] = result
        _emit(on_event, {
            "event_type": "workflow_step_completed",
            "workflow_id": workflow.workflow_id,
            "step_id": step_id,
            "agent_id": step.agent_id,
            "output_key": step.output_key,
            "result_preview": str(result)[:2000],
        })
    except WorkflowExecutionError:
        raise
    except Exception as exc:
        logger.error("Workflow step %s failed: %s", step_id, exc, exc_info=True)
        _emit(on_event, {
            "event_type": "workflow_step_failed",
            "workflow_id": workflow.workflow_id,
            "step_id": step_id,
            "error": str(exc)[:2000],
        })
        raise WorkflowExecutionError(f"Step '{step_id}' failed: {exc}") from exc


def _check_conditions(
    incoming: list[WorkflowEdge],
    outputs: dict[str, Any],
    on_event: Optional[Callable],
    workflow: WorkflowDefinitionSchema,
    step_id: str,
) -> bool:
    for edge in incoming:
        if edge.condition:
            try:
                if not _eval_condition(edge.condition, outputs):
                    _emit(on_event, {
                        "event_type": "workflow_step_skipped",
                        "workflow_id": workflow.workflow_id,
                        "step_id": step_id,
                        "reason": f"condition not met: {edge.condition}",
                    })
                    return True
            except Exception as exc:
                logger.warning("Edge condition eval failed: %s — skipping %s", exc, step_id)
                return True
    return False


# ── B6: Output schema validation ──────────────────────────────────────────────

def _validate_output(
    step: WorkflowStep,
    result: Any,
    workflow_id: str,
    on_event: Optional[Callable],
) -> None:
    if not step.output_schema:
        return
    try:
        import json as _json
        import jsonschema  # type: ignore[import]
        data = result
        if isinstance(result, str):
            try:
                data = _json.loads(result)
            except (ValueError, TypeError):
                pass
        jsonschema.validate(instance=data, schema=step.output_schema)
    except ImportError:
        logger.debug("jsonschema not installed — output_schema validation skipped for step %s", step.step_id)
    except Exception as exc:
        logger.warning("Step %s output failed schema validation: %s", step.step_id, exc)
        _emit(on_event, {
            "event_type": "workflow_step_output_invalid",
            "workflow_id": workflow_id,
            "step_id": step.step_id,
            "validation_error": str(exc)[:500],
        })


# ── Private helpers ────────────────────────────────────────────────────────────

def _run_step_with_retry(
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    workflow_id: str,
    run_id: str,
    on_event: Optional[Callable] = None,
) -> Any:
    """Run a step with exponential backoff retries; dead-letter on exhaustion."""
    last_exc: Exception | None = None
    max_attempts = 1 + step.max_retries

    for attempt in range(1, max_attempts + 1):
        try:
            return _dispatch_step(step, step_inputs, tenant_id, on_event)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Step %s attempt %d/%d failed (%s) — retrying in %.1fs",
                    step.step_id, attempt, max_attempts, exc, delay,
                )
                _emit(on_event, {
                    "event_type": "workflow_step_retrying",
                    "workflow_id": workflow_id,
                    "step_id": step.step_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "delay_s": delay,
                    "error": str(exc)[:500],
                })
                time.sleep(delay)

    # Exhausted retries — record in dead-letter store
    if last_exc is None:
        last_exc = WorkflowExecutionError(f"Step '{step.step_id}' failed with unknown error")

    try:
        from api.services.workflows.dead_letter import record_dead_letter
        record_dead_letter(
            tenant_id=tenant_id,
            run_id=run_id,
            workflow_id=workflow_id,
            step_id=step.step_id,
            error=str(last_exc),
            inputs=step_inputs,
            attempt=max_attempts,
            step_type=step.step_type,
        )
    except Exception as dl_exc:
        logger.error("Failed to record dead-letter for step %s: %s", step.step_id, dl_exc)

    raise last_exc


def _dispatch_step(
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    on_event: Optional[Callable] = None,
) -> Any:
    """Route to the correct handler based on step_type."""
    if step.step_type == "agent" or not step.step_type:
        return _run_agent_step(step.agent_id, step_inputs, tenant_id, on_event)

    from api.services.workflows.nodes import get_handler
    handler = get_handler(step.step_type)
    if handler is None:
        raise ValueError(f"No handler registered for step_type '{step.step_type}'")
    return handler(step, step_inputs, on_event)


def _run_agent_step(
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
    allowed_tool_ids = list(schema.tools) if getattr(schema, "tools", None) else None
    max_tool_calls = getattr(schema, "max_tool_calls_per_run", None)
    result_parts: list[str] = []
    for chunk in run_agent_task(
        task,
        tenant_id=tenant_id,
        system_prompt=schema.system_prompt or None,
        allowed_tool_ids=allowed_tool_ids,
        max_tool_calls=max_tool_calls,
    ):
        text = chunk.get("text") or chunk.get("content") or ""
        if text:
            result_parts.append(str(text))
        if on_event:
            on_event({**chunk, "step_agent_id": agent_id})
    return "".join(result_parts)


def _resolve_inputs(
    input_mapping: dict[str, str],
    outputs: dict[str, Any],
    ctx: Any | None = None,
) -> dict[str, Any]:
    """Resolve input_mapping against available outputs and run context (B7).

    Supports:
      - "literal:value"  → use "value" directly
      - "context:key"    → read from WorkflowRunContext (B7)
      - bare key         → look up outputs[key]
    """
    resolved: dict[str, Any] = {}
    for param, source in input_mapping.items():
        if source.startswith("literal:"):
            resolved[param] = source[len("literal:"):]
        elif source.startswith("context:") and ctx is not None:
            resolved[param] = ctx.read(source[len("context:"):])
        else:
            resolved[param] = outputs.get(source, "")
    return resolved


def _eval_condition(condition: str, outputs: dict[str, Any]) -> bool:
    """Evaluate a workflow edge condition string against step outputs.

    Supports:
      - Compound:  ``A OR B``, ``A AND B``, ``NOT A``  (OR splits first, AND within)
      - Comparison: ``output.key == value``, ``output.key != value``, ``output.key > 5``
      - Truthy:     ``output.key``  (True when value is truthy)
      - Literals:   quoted strings, int/float, True/False/None/null
    """
    import re
    condition = condition.strip()

    # OR (lowest precedence) — split first so AND binds tighter
    if re.search(r'\bOR\b', condition, re.IGNORECASE):
        parts = re.split(r'\bOR\b', condition, flags=re.IGNORECASE)
        return any(_eval_condition(p.strip(), outputs) for p in parts if p.strip())

    # AND
    if re.search(r'\bAND\b', condition, re.IGNORECASE):
        parts = re.split(r'\bAND\b', condition, flags=re.IGNORECASE)
        return all(_eval_condition(p.strip(), outputs) for p in parts if p.strip())

    # NOT
    not_m = re.match(r'^NOT\s+(.+)$', condition, re.IGNORECASE)
    if not_m:
        return not _eval_condition(not_m.group(1).strip(), outputs)

    # Comparison: output.key OP value
    _CMP = re.compile(r'^output\.([A-Za-z_]\w*)\s*(==|!=|>=|<=|>|<)\s*(.+)$')
    m = _CMP.match(condition)
    if m:
        key, op, raw_val = m.group(1), m.group(2), m.group(3).strip()
        lhs = outputs.get(key)
        rhs: Any
        if (raw_val.startswith('"') and raw_val.endswith('"')) or \
           (raw_val.startswith("'") and raw_val.endswith("'")):
            rhs = raw_val[1:-1]
        elif raw_val in ("True", "true"):
            rhs = True
        elif raw_val in ("False", "false"):
            rhs = False
        elif raw_val in ("None", "null"):
            rhs = None
        else:
            try:
                rhs = int(raw_val)
            except ValueError:
                try:
                    rhs = float(raw_val)
                except ValueError:
                    rhs = raw_val
        if op == "==":
            return lhs == rhs
        if op == "!=":
            return lhs != rhs
        try:
            lhs_n, rhs_n = float(lhs), float(rhs)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return {">" : lhs_n > rhs_n, ">=" : lhs_n >= rhs_n,
                "<" : lhs_n < rhs_n, "<=" : lhs_n <= rhs_n}.get(op, False)

    # Truthy: output.key
    _TRUTHY = re.compile(r'^output\.([A-Za-z_]\w*)$')
    m2 = _TRUTHY.match(condition)
    if m2:
        return bool(outputs.get(m2.group(1)))

    logger.warning("Unsupported workflow condition syntax (skipping): %r", condition)
    return False


def _emit(on_event: Optional[Callable], event: dict[str, Any]) -> None:
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass


def _format_inputs(inputs: dict[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in inputs.items())
