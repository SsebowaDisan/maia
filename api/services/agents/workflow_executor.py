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

    # Per-worker cost tracking — stored in context for step-level access
    cost_tracker = None
    try:
        from api.services.workflows.per_worker_cost import WorkflowCostTracker
        cost_tracker = WorkflowCostTracker(run_id=effective_run_id)
        ctx.write("__cost_tracker", cost_tracker)
    except Exception:
        pass

    try:
        ordered_ids = workflow.topological_order()
    except ValueError as exc:
        raise WorkflowExecutionError(str(exc)) from exc

    # Store workflow agent IDs/roster in context for real cross-agent collaboration.
    workflow_agent_ids = list({s.agent_id for s in workflow.steps if s.agent_id})
    workflow_agent_roster: list[dict[str, str]] = []
    seen_agent_ids: set[str] = set()
    for step in workflow.steps:
        agent_id = str(step.agent_id or "").strip()
        if not agent_id or agent_id in seen_agent_ids:
            continue
        seen_agent_ids.add(agent_id)
        workflow_agent_roster.append(
            {
                "agent_id": agent_id,
                "step_id": str(step.step_id or "").strip(),
                "step_description": str(step.description or "").strip(),
            }
        )
    ctx.write("__workflow_agent_ids", workflow_agent_ids)
    ctx.write("__workflow_agent_roster", workflow_agent_roster)

    # Dynamic dependency tracking for runtime unblocking visibility
    task_dag = None
    try:
        from api.services.workflows.task_dag import TaskDAG
        task_dag = TaskDAG.from_workflow(workflow)
    except Exception:
        pass

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
                if task_dag:
                    task_dag.mark_skipped(step_id)
                _emit(on_event, {
                    "event_type": "workflow_step_skipped",
                    "workflow_id": workflow.workflow_id,
                    "step_id": step_id,
                    "reason": "predecessor_skipped",
                })
                continue
            if _check_conditions(incoming, outputs, on_event, workflow, step_id):
                skipped_steps.add(step_id)
                if task_dag:
                    task_dag.mark_skipped(step_id)
            else:
                runnable.append(step_id)
                if task_dag:
                    task_dag.mark_running(step_id)
                if cost_tracker:
                    cost_tracker.start_step(step_id, step.agent_id if step else "")

        if not runnable:
            continue

        if len(runnable) == 1:
            _execute_step(workflow, runnable[0], outputs, outputs_lock, ctx, tenant_id, on_event, skipped_steps, step_timeout_s, effective_run_id)
        else:
            # B8: Run independent steps concurrently
            _execute_batch(workflow, runnable, outputs, outputs_lock, ctx, tenant_id, on_event, skipped_steps, step_timeout_s, effective_run_id)

        # Update DAG + cost for completed/failed steps in this batch
        for step_id in runnable:
            if step_id in skipped_steps:
                continue
            if cost_tracker:
                cost_tracker.end_step(step_id)
                # Estimate cost from result length as a rough proxy
                result = outputs.get(workflow.get_step(step_id).output_key if workflow.get_step(step_id) else "", "")
                result_len = len(str(result or ""))
                cost_tracker.record(step_id=step_id, agent_id=workflow.get_step(step_id).agent_id if workflow.get_step(step_id) else "", tokens_in=result_len // 4, tokens_out=result_len // 4)
            if task_dag:
                if step_id in outputs or any(workflow.get_step(step_id) and workflow.get_step(step_id).output_key in outputs for _ in [1]):
                    newly_ready = task_dag.mark_completed(step_id)
                    if newly_ready:
                        _emit(on_event, {"event_type": "workflow_steps_unblocked", "workflow_id": workflow.workflow_id, "unblocked": newly_ready})
                else:
                    task_dag.mark_failed(step_id)

    # Emit cost breakdown with completion
    cost_summary = cost_tracker.summary() if cost_tracker else {}
    _emit(on_event, {
        "event_type": "workflow_completed",
        "workflow_id": workflow.workflow_id,
        "run_id": effective_run_id,
        "outputs": {k: str(v)[:200] for k, v in outputs.items()},
        "cost_summary": cost_summary,
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
        # Inject handoff context from predecessor step
        _inject_handoff_context(workflow, step, step_inputs, outputs, run_id)
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


# ── Stage contract validation ─────────────────────────────────────────────────

def _validate_stage_contract(
    step: WorkflowStep,
    phase: str,
    data: dict[str, Any],
    workflow_id: str,
    on_event: Optional[Callable],
) -> None:
    """Validate inputs or outputs against the step type's stage contract."""
    try:
        from api.services.workflows.stage_contracts import validate_step_boundary
        errors = validate_step_boundary(step_type=step.step_type, phase=phase, data=data if isinstance(data, dict) else {})
        if errors:
            logger.warning("Step %s %s contract violation: %s", step.step_id, phase, errors)
            _emit(on_event, {
                "event_type": f"workflow_step_{phase}_contract_violation",
                "workflow_id": workflow_id,
                "step_id": step.step_id,
                "violations": errors,
            })
    except Exception:
        pass


# ── Quality gate ──────────────────────────────────────────────────────────────

def _run_quality_gate(
    step: WorkflowStep,
    result: Any,
    workflow_id: str,
    on_event: Optional[Callable],
) -> None:
    """Check output quality for agent steps (detect placeholders, filler)."""
    if step.step_type not in ("agent", ""):
        return
    text = str(result or "")
    if len(text) < 50:
        return
    try:
        from api.services.agent.reasoning.quality_gate import check_output_quality
        qr = check_output_quality(text)
        if not qr["passed"]:
            logger.warning("Step %s quality gate failed: %s", step.step_id, qr["issues"])
            _emit(on_event, {
                "event_type": "workflow_step_quality_warning",
                "workflow_id": workflow_id,
                "step_id": step.step_id,
                "quality_score": qr["score"],
                "issues": [i["message"] for i in qr["issues"]],
            })
    except Exception:
        pass


# ── Brain review — reviews agent output between workflow steps ─────────────────

def _run_brain_review(
    step: WorkflowStep,
    result: Any,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str,
    on_event: Optional[Callable],
) -> Any:
    """Run Brain review loop on agent step output. Returns potentially revised output."""
    if step.step_type not in ("agent", ""):
        return result
    text_result = str(result or "")
    if len(text_result) < 50:
        return result
    try:
        import os
        if os.getenv("MAIA_BRAIN_REVIEW_ENABLED", "true").strip().lower() in ("false", "0", "no"):
            return result

        from api.services.agent.brain.review_loop import brain_review_loop

        original_task = str(step_inputs.get("message") or step_inputs.get("task") or step.description or "")

        def _run_agent_as(target_agent: str, prompt: str) -> str:
            agent_id = str(target_agent or "").strip() or str(step.agent_id or step.step_id).strip()
            if not agent_id:
                return ""
            agent_output = _run_agent_step(
                agent_id,
                {"message": prompt},
                tenant_id,
                on_event,
            )
            return str(agent_output or "")

        def _rerun_agent(prompt: str) -> str:
            # Re-run with the same agent profile rather than a generic LLM call.
            current_agent_id = str(step.agent_id or step.step_id).strip()
            return _run_agent_as(current_agent_id, prompt)

        reviewed_output, review_history = brain_review_loop(
            agent_id=step.agent_id or step.step_id,
            step_id=step.step_id,
            step_description=step.description,
            original_task=original_task,
            initial_output=text_result,
            run_id=run_id,
            tenant_id=tenant_id,
            on_event=on_event,
            run_agent_fn=_rerun_agent,
        )
        # Record review stats for the run summary
        if review_history:
            revisions = sum(1 for r in review_history if r.get("decision") == "revise")
            questions = sum(1 for r in review_history if r.get("decision") == "question")
            if revisions or questions:
                _emit(on_event, {
                    "event_type": "brain_review_summary",
                    "step_id": step.step_id,
                    "data": {"revisions": revisions, "questions": questions, "rounds": len(review_history)},
                })

        # Dialogue detection — check if agent needs input from a teammate
        reviewed_output = _run_dialogue_detection(
            step,
            reviewed_output,
            tenant_id,
            run_id,
            on_event,
            run_agent_for_agent_fn=_run_agent_as,
        )

        return reviewed_output
    except Exception as exc:
        logger.debug("Brain review skipped: %s", exc)
        return result


# ── Dialogue detection — check if agents should talk to each other ─────────────

def _run_dialogue_detection(
    step: WorkflowStep,
    output: str,
    tenant_id: str,
    run_id: str,
    on_event: Optional[Callable],
    run_agent_for_agent_fn: Optional[Callable[[str, str], str]] = None,
) -> str:
    """Detect if the agent needs input from a teammate and facilitate the dialogue."""
    try:
        import os
        if os.getenv("MAIA_DIALOGUE_ENABLED", "true").strip().lower() in ("false", "0", "no"):
            return output

        from api.services.agent.brain.dialogue_detector import (
            detect_dialogue_needs,
            evaluate_dialogue_follow_up,
        )
        from api.services.agent.dialogue_turns import get_dialogue_service

        # Get available agent roles from the workflow run context
        try:
            from api.services.agents.workflow_context import WorkflowRunContext
            run_ctx = WorkflowRunContext(run_id) if run_id else None
            available_agents = run_ctx.read("__workflow_agent_ids") if run_ctx else []
            available_roster = run_ctx.read("__workflow_agent_roster") if run_ctx else []
        except Exception:
            available_agents = []
            available_roster = []
        if not isinstance(available_agents, list):
            available_agents = []
        if not available_agents:
            return output
        if not isinstance(available_roster, list):
            available_roster = []

        needs = detect_dialogue_needs(
            agent_output=output,
            current_agent=step.agent_id or step.step_id,
            available_agents=available_agents,
            agent_roster=available_roster,
            step_description=step.description,
            tenant_id=tenant_id,
        )
        if not needs:
            return output

        dialogue_svc = get_dialogue_service()
        source_agent = str(step.agent_id or step.step_id or "agent").strip() or "agent"
        enrichments: list[str] = []

        for need in needs:
            target = need.get("target_agent", "")
            question = need.get("question", "")
            if not target or not question:
                continue
            interaction_type = _normalize_dialogue_turn_type(need.get("interaction_type", "question"))
            interaction_label = str(need.get("interaction_label", "")).strip() or _default_interaction_label(interaction_type)
            scene_family = _normalize_dialogue_scene_family(need.get("scene_family"))
            scene_surface = _normalize_dialogue_scene_surface(need.get("scene_surface"), scene_family=scene_family)
            operation_label = str(need.get("operation_label", "")).strip()[:160]
            action = _dialogue_action_for_surface(scene_surface=scene_surface, scene_family=scene_family)
            reason = str(need.get("reason", "")).strip()
            request_text = question
            if reason:
                request_text = f"{question}\n\nWhy this matters: {reason}"
            prompt_preamble = _build_dialogue_prompt_preamble(
                interaction_label=interaction_label,
                reason=reason,
            )
            response_turn_type = _derive_response_turn_type(interaction_type)

            _emit(on_event, {
                "event_type": "agent_dialogue_started",
                "title": f"{source_agent} needs input from {target}",
                "detail": request_text[:200],
                "data": {
                    "from_agent": source_agent,
                    "to_agent": target,
                    "run_id": run_id,
                    "turn_role": "request",
                    "turn_type": interaction_type,
                    "interaction_type": interaction_type,
                    "interaction_label": interaction_label,
                    "scene_family": scene_family,
                    "scene_surface": scene_surface,
                    "operation_label": operation_label or interaction_label,
                    "action": action,
                    "action_phase": "active",
                    "action_status": "in_progress",
                },
            })

            answer = dialogue_svc.ask(
                run_id=run_id,
                from_agent=source_agent,
                to_agent=target,
                question=request_text,
                tenant_id=tenant_id,
                on_event=on_event,
                answer_fn=run_agent_for_agent_fn,
                ask_turn_type=interaction_type,
                answer_turn_type=response_turn_type,
                ask_turn_role="request",
                answer_turn_role="response",
                interaction_label=interaction_label,
                scene_family=scene_family,
                scene_surface=scene_surface,
                operation_label=operation_label,
                action=action,
                action_phase="active",
                action_status="in_progress",
                prompt_preamble=prompt_preamble,
            )

            follow_up = evaluate_dialogue_follow_up(
                source_agent=source_agent,
                target_agent=target,
                interaction_type=interaction_type,
                initial_request=request_text,
                teammate_response=str(answer or ""),
                source_output=str(output or ""),
                tenant_id=tenant_id,
            )
            if follow_up.get("requires_follow_up") and run_agent_for_agent_fn:
                follow_up_prompt = str(follow_up.get("follow_up_prompt", "")).strip()
                follow_up_type = _normalize_dialogue_turn_type(
                    follow_up.get("follow_up_type", interaction_type),
                )
                follow_up_label = (
                    str(follow_up.get("follow_up_label", "")).strip()
                    or str(follow_up.get("reason", "")).strip()
                    or interaction_label
                )
                follow_up_scene_family = scene_family
                follow_up_scene_surface = scene_surface
                follow_up_operation_label = operation_label
                follow_up_action = action
                if follow_up_prompt:
                    answer = dialogue_svc.ask(
                        run_id=run_id,
                        from_agent=source_agent,
                        to_agent=target,
                        question=follow_up_prompt,
                        tenant_id=tenant_id,
                        on_event=on_event,
                        answer_fn=run_agent_for_agent_fn,
                        ask_turn_type=follow_up_type,
                        answer_turn_type=_derive_response_turn_type(follow_up_type),
                        ask_turn_role="request",
                        answer_turn_role="response",
                        interaction_label=follow_up_label,
                        scene_family=follow_up_scene_family,
                        scene_surface=follow_up_scene_surface,
                        operation_label=follow_up_operation_label,
                        action=follow_up_action,
                        action_phase="active",
                        action_status="in_progress",
                        prompt_preamble=_build_dialogue_prompt_preamble(
                            interaction_label=follow_up_label,
                            reason=str(follow_up.get("reason", "")).strip(),
                        ),
                    )

            integrated = False
            if run_agent_for_agent_fn:
                try:
                    integration_prompt = (
                        f"You are {source_agent}. You asked teammate {target}: {question}\n\n"
                        f"Teammate answer:\n{answer}\n\n"
                        f"Your current step output:\n{output[:3500]}\n\n"
                        "Revise your output to integrate valid teammate insights. "
                        "If you disagree with a point, state why with evidence."
                    )
                    revised_output = run_agent_for_agent_fn(source_agent, integration_prompt)
                    revised_text = str(revised_output or "").strip()
                    if revised_text:
                        output = revised_text
                        integrated = True
                        _emit(on_event, {
                            "event_type": "agent_dialogue_turn",
                            "title": f"{source_agent} integrated teammate input",
                            "detail": revised_text[:300],
                            "stage": "execute",
                            "status": "info",
                            "data": {
                                "run_id": run_id,
                                "from_agent": source_agent,
                                "to_agent": "team",
                                "turn_type": "integration",
                                "turn_role": "integration",
                                "interaction_label": "integrated teammate feedback",
                                "scene_family": scene_family,
                                "scene_surface": scene_surface,
                                "operation_label": operation_label or "Integrate teammate feedback",
                                "action": action,
                                "action_phase": "completed",
                                "action_status": "ok",
                                "message": revised_text[:1000],
                            },
                        })
                except Exception as exc:
                    logger.debug("Dialogue integration skipped: %s", exc)

            if not integrated:
                enrichments.append(f"[From {target}]: {answer}")

            _emit(on_event, {
                "event_type": "agent_dialogue_resolved",
                "title": f"Dialogue resolved: {source_agent} ← {target}",
                "detail": answer[:200],
                "data": {
                    "from_agent": target,
                    "to_agent": source_agent,
                    "run_id": run_id,
                    "turn_role": "response",
                    "scene_family": scene_family,
                    "scene_surface": scene_surface,
                    "operation_label": operation_label or interaction_label,
                    "action": action,
                    "action_phase": "completed",
                    "action_status": "ok",
                },
            })

        if enrichments:
            output = f"{output}\n\n--- Additional context from team dialogue ---\n" + "\n".join(enrichments)

        return output
    except Exception as exc:
        logger.debug("Dialogue detection skipped: %s", exc)
        return output


# ── Evolution store — record lessons from failures ────────────────────────────

def _normalize_dialogue_turn_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "question"
    return "_".join(part for part in raw.replace("-", "_").split("_") if part) or "question"


def _derive_response_turn_type(request_turn_type: str) -> str:
    normalized = _normalize_dialogue_turn_type(request_turn_type)
    if normalized.endswith("_request"):
        return f"{normalized[:-8]}_response".strip("_")
    if normalized.endswith("_question"):
        return f"{normalized[:-9]}_response".strip("_")
    if normalized.endswith("_response") or normalized.endswith("_answer"):
        return normalized
    if normalized in {"question", "request"}:
        return "response"
    return f"{normalized}_response"


def _default_interaction_label(turn_type: str) -> str:
    normalized = _normalize_dialogue_turn_type(turn_type)
    if normalized.endswith("_request"):
        normalized = normalized[:-8]
    return normalized.replace("_", " ").strip() or "teammate input"


def _normalize_dialogue_scene_family(value: Any) -> str:
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


def _normalize_dialogue_scene_surface(value: Any, *, scene_family: str = "") -> str:
    normalized = str(value or "").strip().lower()
    allowed = {"email", "google_sheets", "google_docs", "api", "website", "system"}
    if normalized in allowed:
        return normalized

    family = _normalize_dialogue_scene_family(scene_family)
    if family == "email":
        return "email"
    if family == "sheet":
        return "google_sheets"
    if family == "document":
        return "google_docs"
    if family == "browser":
        return "website"
    if family in {"api", "chat", "crm", "support", "commerce"}:
        return "api"
    return ""


def _dialogue_action_for_surface(*, scene_surface: str, scene_family: str) -> str:
    surface = str(scene_surface or "").strip().lower()
    family = _normalize_dialogue_scene_family(scene_family)
    if surface == "email" or family == "email":
        return "type"
    if surface in {"google_docs", "google_sheets"} or family in {"document", "sheet"}:
        return "type"
    if surface == "website" or family == "browser":
        return "navigate"
    if surface == "api" or family in {"api", "chat", "crm", "support", "commerce"}:
        return "verify"
    return "other"


def _build_dialogue_prompt_preamble(*, interaction_label: str, reason: str) -> str:
    label = str(interaction_label or "").strip()
    reason_text = str(reason or "").strip()
    if label and reason_text:
        return (
            f"Collaboration style: {label}. "
            f"Respond with the evidence, correction, or revision needed. Context: {reason_text}"
        )
    if label:
        return f"Collaboration style: {label}. Respond clearly with concrete supporting detail."
    if reason_text:
        return f"Respond with concise, actionable input. Context: {reason_text}"
    return "Respond with concise, actionable teammate input."


def _record_failure_lesson(tenant_id: str, step: WorkflowStep, error: str, run_id: str) -> None:
    """Record a lesson when a step fails, for cross-run learning."""
    try:
        from api.services.agent.reasoning.evolution_store import EvolutionStore
        store = EvolutionStore(tenant_id=tenant_id)
        store.record_failure_lesson(step_id=step.step_id, error=error, run_id=run_id)
    except Exception:
        pass


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
    # Validate input contract
    _validate_stage_contract(step, "input", step_inputs, workflow_id, on_event)

    last_exc: Exception | None = None
    max_attempts = 1 + step.max_retries

    for attempt in range(1, max_attempts + 1):
        try:
            result = _dispatch_step(step, step_inputs, tenant_id, on_event)
            # Validate output contract + quality gate
            _validate_stage_contract(step, "output", result if isinstance(result, dict) else {}, workflow_id, on_event)
            _run_quality_gate(step, result, workflow_id, on_event)
            # Brain review for agent steps
            result = _run_brain_review(step, result, step_inputs, tenant_id, run_id, on_event)
            return result
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

    # Exhausted retries — record lesson for cross-run learning + dead-letter store
    if last_exc is None:
        last_exc = WorkflowExecutionError(f"Step '{step.step_id}' failed with unknown error")
    _record_failure_lesson(tenant_id, step, str(last_exc)[:300], run_id)

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
    # Check approval gates for sensitive actions
    try:
        from api.services.agent.approval_workflows import get_approval_service
        service = get_approval_service()
        tool_ids = [t for t in (step.step_config.get("tool_ids") or []) if service.requires_approval(t, tenant_id)]
        if tool_ids:
            gate = service.create_gate(run_id="", tool_id=tool_ids[0], params=step_inputs, connector_id=step.step_config.get("connector_id", ""))
            logger.info("Approval gate created for step %s: %s", step.step_id, gate.gate_id)
    except Exception:
        pass

    if step.step_type == "agent" or not step.step_type:
        return _run_agent_step(
            step.agent_id,
            step_inputs,
            tenant_id,
            on_event,
            step=step,
        )

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
    step: WorkflowStep | None = None,
) -> Any:
    from api.services.agents.definition_store import get_agent, load_schema
    from api.services.agents.runner import run_agent_task

    record = get_agent(tenant_id, agent_id)
    if not record:
        raise ValueError(f"Agent '{agent_id}' not found in tenant '{tenant_id}'.")

    schema = load_schema(record)

    # Inject evolution store lessons as prompt overlay
    system_prompt = schema.system_prompt or ""
    system_prompt = _inject_evolution_overlay(tenant_id, agent_id, system_prompt)

    # Inject handoff context from previous agent if available
    handoff_context = step_inputs.pop("__handoff_context", None)
    if handoff_context and isinstance(handoff_context, str):
        system_prompt = f"{system_prompt}\n\n{handoff_context}" if system_prompt else handoff_context

    task = step_inputs.get("message") or step_inputs.get("task") or (
        f"Execute your task with the following context:\n{_format_inputs(step_inputs)}"
    )
    schema_tool_ids = (
        [str(tool_id).strip() for tool_id in list(getattr(schema, "tools", []) or []) if str(tool_id).strip()]
        if getattr(schema, "tools", None) is not None
        else []
    )
    step_tool_ids: list[str] | None = None
    if step is not None and isinstance(step.step_config, dict) and "tool_ids" in step.step_config:
        raw_step_tools = step.step_config.get("tool_ids")
        if isinstance(raw_step_tools, list):
            step_tool_ids = [
                str(tool_id).strip()
                for tool_id in raw_step_tools
                if str(tool_id).strip()
            ]
        else:
            step_tool_ids = []

    if step_tool_ids is not None:
        if schema_tool_ids:
            allowed_tool_ids = [tool_id for tool_id in step_tool_ids if tool_id in set(schema_tool_ids)]
        else:
            allowed_tool_ids = list(step_tool_ids)
    else:
        allowed_tool_ids = list(schema_tool_ids) if schema_tool_ids else None

    max_tool_calls = getattr(schema, "max_tool_calls_per_run", None)
    result_parts: list[str] = []
    for chunk in run_agent_task(
        task,
        tenant_id=tenant_id,
        system_prompt=system_prompt or None,
        allowed_tool_ids=allowed_tool_ids,
        max_tool_calls=max_tool_calls,
    ):
        text = chunk.get("text") or chunk.get("content") or chunk.get("delta") or ""
        if text:
            result_parts.append(str(text))
        if on_event:
            # run_agent_task proxies AgentOrchestrator.run_stream(), which emits
            # {type:"activity", event:{...}} records. Unwrap activity payloads so
            # workflow SSE receives real event_type entries instead of generic "event".
            if (
                isinstance(chunk, dict)
                and str(chunk.get("type") or "").strip().lower() == "activity"
                and isinstance(chunk.get("event"), dict)
            ):
                on_event({**chunk["event"], "step_agent_id": agent_id})
            elif isinstance(chunk, dict) and str(chunk.get("event_type") or "").strip():
                on_event({**chunk, "step_agent_id": agent_id})

    raw_result = "".join(result_parts)

    # Citation verification for agent output
    raw_result = _verify_and_clean_citations(raw_result, tenant_id)

    return raw_result


def _inject_evolution_overlay(tenant_id: str, agent_id: str, system_prompt: str) -> str:
    """Inject cross-run lessons into the agent's system prompt."""
    try:
        from api.services.agent.reasoning.evolution_store import EvolutionStore
        store = EvolutionStore(tenant_id=tenant_id)
        overlay = store.get_prompt_overlay(stage=agent_id, max_lessons=5)
        if overlay:
            return f"{system_prompt}\n\n{overlay}" if system_prompt else overlay
    except Exception:
        pass
    return system_prompt


def _verify_and_clean_citations(text: str, tenant_id: str) -> str:
    """Verify citations in agent output and strip hallucinated ones."""
    if not text or len(text) < 100:
        return text
    try:
        from api.services.agent.reasoning.citation_verify import verify_citations, strip_hallucinated_citations
        # Get list of uploaded filenames for L1 verification
        filenames: list[str] = []
        try:
            from api.context import get_context
            ctx = get_context()
            index = ctx.get_index()
            Source = index._resources.get("Source")
            if Source:
                from sqlmodel import Session, select
                from ktem.db.engine import engine
                with Session(engine) as session:
                    rows = session.exec(select(Source.name)).all()
                    filenames = [str(r) for r in rows if r]
        except Exception:
            pass

        results = verify_citations(text, uploaded_filenames=filenames)
        if results:
            hallucinated = [r for r in results if r["status"] == "hallucinated"]
            if hallucinated:
                logger.info("Stripping %d hallucinated citations from agent output", len(hallucinated))
                text = strip_hallucinated_citations(text, results)
    except Exception:
        pass
    return text


def _inject_handoff_context(
    workflow: Any,
    step: Any,
    step_inputs: dict[str, Any],
    outputs: dict[str, Any],
    run_id: str,
) -> None:
    """Build and inject handoff context from the predecessor agent."""
    if step.step_type not in ("agent", ""):
        return
    try:
        from api.services.agent.handoff_manager import build_handoff_context
        # Find predecessor step(s)
        incoming_edges = [e for e in workflow.edges if e.to_step == step.step_id]
        if not incoming_edges:
            return
        prev_step_id = incoming_edges[0].from_step
        prev_step = workflow.get_step(prev_step_id)
        if not prev_step:
            return
        prev_output = str(outputs.get(prev_step.output_key, ""))
        if not prev_output:
            return
        context = build_handoff_context(
            from_agent=prev_step.agent_id or prev_step_id,
            to_agent=step.agent_id or step.step_id,
            from_step_id=prev_step_id,
            to_step_id=step.step_id,
            previous_output=prev_output,
            step_description=step.description,
            run_id=run_id,
        )
        step_inputs["__handoff_context"] = context.to_prompt_context()
    except Exception:
        pass


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
