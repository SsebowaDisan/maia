from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeout, as_completed
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowDefinitionSchema, WorkflowEdge, WorkflowStep

from .common import WorkflowExecutionError, _emit, _MAX_PARALLEL_STEPS, _eval_condition, logger


def execute_workflow(
    workflow: WorkflowDefinitionSchema,
    tenant_id: str,
    *,
    initial_inputs: dict[str, Any] | None = None,
    on_event: Optional[Callable[[dict[str, Any]], None]] = None,
    run_id: str | None = None,
    step_timeout_s: int = 300,
    ops: Any,
) -> dict[str, Any]:
    from api.services.agents.workflow_context import WorkflowRunContext, cleanup_context

    effective_run_id = run_id or str(uuid.uuid4())
    ctx = WorkflowRunContext(effective_run_id)
    outputs: dict[str, Any] = dict(initial_inputs or {})
    outputs_lock = threading.Lock()
    skipped_steps: set[str] = set()

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

    workflow_agent_ids: list[str] = []
    seen_workflow_agent_ids: set[str] = set()
    for step in workflow.steps:
        agent_id = str(step.agent_id or "").strip()
        if agent_id and agent_id not in seen_workflow_agent_ids:
            seen_workflow_agent_ids.add(agent_id)
            workflow_agent_ids.append(agent_id)

    workflow_agent_roster: list[dict[str, str]] = []
    seen_agent_ids: set[str] = set()
    for step in workflow.steps:
        agent_id = str(step.agent_id or "").strip()
        if not agent_id or agent_id in seen_agent_ids:
            continue
        seen_agent_ids.add(agent_id)
        role_hint = str(step.step_config.get("role") or "").strip() if isinstance(step.step_config, dict) else ""
        display_name = str(step.step_config.get("name") or "").strip() if isinstance(step.step_config, dict) else ""
        if not display_name:
            display_name = agent_id.replace("_", " ").replace("-", " ").strip().title() or agent_id
        workflow_agent_roster.append(
            {
                "id": agent_id,
                "agent_id": agent_id,
                "name": display_name,
                "role": role_hint or "agent",
                "step_id": str(step.step_id or "").strip(),
                "step_description": str(step.description or "").strip(),
            }
        )
    workflow_agent_roster = ops._ensure_supervisor_in_roster(workflow_agent_roster, workflow=workflow)
    ctx.write("__workflow_agent_ids", workflow_agent_ids)
    ctx.write("__workflow_agent_roster", workflow_agent_roster)

    task_dag = None
    try:
        from api.services.workflows.task_dag import TaskDAG
        task_dag = TaskDAG.from_workflow(workflow)
    except Exception:
        pass

    _emit(on_event, {"event_type": "workflow_started", "workflow_id": workflow.workflow_id, "step_count": len(workflow.steps), "step_order": ordered_ids, "run_id": effective_run_id})
    batches = ops._build_parallel_batches(workflow, ordered_ids)

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
                _emit(on_event, {"event_type": "workflow_step_skipped", "workflow_id": workflow.workflow_id, "step_id": step_id, "reason": "predecessor_skipped"})
                continue
            if ops._check_conditions(incoming, outputs, on_event, workflow, step_id):
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
            ops._execute_step(workflow, runnable[0], outputs, outputs_lock, ctx, tenant_id, on_event, skipped_steps, step_timeout_s, effective_run_id)
        else:
            ops._execute_batch(workflow, runnable, outputs, outputs_lock, ctx, tenant_id, on_event, skipped_steps, step_timeout_s, effective_run_id)

        for step_id in runnable:
            if step_id in skipped_steps:
                continue
            if cost_tracker:
                cost_tracker.end_step(step_id)
                step_obj = workflow.get_step(step_id)
                result = outputs.get(step_obj.output_key if step_obj else "", "")
                result_len = len(str(result or ""))
                cost_tracker.record(step_id=step_id, agent_id=step_obj.agent_id if step_obj else "", tokens_in=result_len // 4, tokens_out=result_len // 4)
            if task_dag:
                step_obj = workflow.get_step(step_id)
                if step_id in outputs or any(step_obj and step_obj.output_key in outputs for _ in [1]):
                    newly_ready = task_dag.mark_completed(step_id)
                    if newly_ready:
                        _emit(on_event, {"event_type": "workflow_steps_unblocked", "workflow_id": workflow.workflow_id, "unblocked": newly_ready})
                else:
                    task_dag.mark_failed(step_id)

    cost_summary = cost_tracker.summary() if cost_tracker else {}
    _emit(on_event, {"event_type": "workflow_completed", "workflow_id": workflow.workflow_id, "run_id": effective_run_id, "outputs": {k: str(v)[:6000] for k, v in outputs.items()}, "cost_summary": cost_summary})
    cleanup_context(effective_run_id)
    return outputs


def _build_parallel_batches(workflow: WorkflowDefinitionSchema, ordered_ids: list[str]) -> list[list[str]]:
    deps: dict[str, set[str]] = {s.step_id: set() for s in workflow.steps}
    for edge in workflow.edges:
        deps[edge.to_step].add(edge.from_step)

    batches: list[list[str]] = []
    completed: set[str] = set()
    remaining = list(ordered_ids)
    while remaining:
        batch = [sid for sid in remaining if deps[sid].issubset(completed)]
        if not batch:
            batch = [remaining[0]]
        batches.append(batch)
        for sid in batch:
            remaining.remove(sid)
            completed.add(sid)
    return batches


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
    ops: Any | None = None,
) -> None:
    cap = min(len(step_ids), _MAX_PARALLEL_STEPS)
    futures = {}
    step_timeouts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=cap, thread_name_prefix="wf-step") as pool:
        for step_id in step_ids:
            step = workflow.get_step(step_id)
            if step is None:
                continue
            with outputs_lock:
                step_inputs = ops._resolve_inputs(step.input_mapping, outputs, ctx)
            _emit(on_event, {"event_type": "workflow_step_started", "workflow_id": workflow.workflow_id, "step_id": step_id, "agent_id": step.agent_id, "step_type": step.step_type, "parallel": True})
            timeout = step.timeout_s or step_timeout_s
            step_timeouts[step.step_id] = timeout
            futures[pool.submit(ops._run_step_with_retry, step, step_inputs, tenant_id, workflow.workflow_id, run_id, on_event, timeout)] = (step, timeout)

        batch_timeout = max(step_timeouts.values(), default=step_timeout_s) + 10
        for future in as_completed(futures, timeout=batch_timeout):
            step, timeout = futures[future]
            try:
                result = future.result(timeout=timeout)
                ops._validate_output(step, result, workflow.workflow_id, on_event)
                with outputs_lock:
                    outputs[step.output_key] = result
                _emit(on_event, {"event_type": "workflow_step_completed", "workflow_id": workflow.workflow_id, "step_id": step.step_id, "agent_id": step.agent_id, "output_key": step.output_key, "result_preview": str(result)[:2000]})
            except _FuturesTimeout as exc:
                _emit(on_event, {"event_type": "workflow_step_failed", "workflow_id": workflow.workflow_id, "step_id": step.step_id, "error": f"Step timed out after {timeout}s"})
                raise WorkflowExecutionError(f"Step '{step.step_id}' timed out after {timeout}s") from exc
            except Exception as exc:
                logger.error("Workflow step %s failed: %s", step.step_id, exc, exc_info=True)
                _emit(on_event, {"event_type": "workflow_step_failed", "workflow_id": workflow.workflow_id, "step_id": step.step_id, "error": str(exc)[:2000]})
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
    ops: Any | None = None,
) -> None:
    step = workflow.get_step(step_id)
    if step is None:
        return
    with outputs_lock:
        step_inputs = ops._resolve_inputs(step.input_mapping, outputs, ctx)
        ops._inject_handoff_context(workflow, step, step_inputs, outputs, run_id, on_event)
    timeout = step.timeout_s or step_timeout_s
    _emit(on_event, {"event_type": "workflow_step_started", "workflow_id": workflow.workflow_id, "step_id": step_id, "agent_id": step.agent_id, "step_type": step.step_type, "parallel": False})
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="wf-step-to") as pool:
            future = pool.submit(ops._run_step_with_retry, step, step_inputs, tenant_id, workflow.workflow_id, run_id, on_event, timeout)
            try:
                result = future.result(timeout=timeout)
            except _FuturesTimeout as exc:
                raise TimeoutError(f"Step '{step_id}' timed out after {timeout}s") from exc
        ops._validate_output(step, result, workflow.workflow_id, on_event)
        with outputs_lock:
            outputs[step.output_key] = result
        _emit(on_event, {"event_type": "workflow_step_completed", "workflow_id": workflow.workflow_id, "step_id": step_id, "agent_id": step.agent_id, "output_key": step.output_key, "result_preview": str(result)[:2000]})
    except WorkflowExecutionError:
        raise
    except Exception as exc:
        logger.error("Workflow step %s failed: %s", step_id, exc, exc_info=True)
        _emit(on_event, {"event_type": "workflow_step_failed", "workflow_id": workflow.workflow_id, "step_id": step_id, "error": str(exc)[:2000]})
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
                    _emit(on_event, {"event_type": "workflow_step_skipped", "workflow_id": workflow.workflow_id, "step_id": step_id, "reason": f"condition not met: {edge.condition}"})
                    return True
            except Exception as exc:
                logger.warning("Edge condition eval failed: %s - skipping %s", exc, step_id)
                return True
    return False


def _validate_output(step: WorkflowStep, result: Any, workflow_id: str, on_event: Optional[Callable]) -> None:
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
        logger.debug("jsonschema not installed - output_schema validation skipped for step %s", step.step_id)
    except Exception as exc:
        logger.warning("Step %s output failed schema validation: %s", step.step_id, exc)
        _emit(on_event, {"event_type": "workflow_step_output_invalid", "workflow_id": workflow_id, "step_id": step.step_id, "validation_error": str(exc)[:500]})


def _validate_stage_contract(step: WorkflowStep, phase: str, data: dict[str, Any], workflow_id: str, on_event: Optional[Callable]) -> None:
    try:
        from api.services.workflows.stage_contracts import validate_step_boundary
        errors = validate_step_boundary(step_type=step.step_type, phase=phase, data=data if isinstance(data, dict) else {})
        if errors:
            logger.warning("Step %s %s contract violation: %s", step.step_id, phase, errors)
            _emit(on_event, {"event_type": f"workflow_step_{phase}_contract_violation", "workflow_id": workflow_id, "step_id": step.step_id, "violations": errors})
    except Exception:
        pass


def _run_quality_gate(step: WorkflowStep, result: Any, workflow_id: str, on_event: Optional[Callable]) -> None:
    if step.step_type not in ("agent", ""):
        return
    text = str(result or "")
    if len(text) < 50:
        return
    try:
        from api.services.agent.reasoning.quality_gate import check_output_quality
        qr = check_output_quality(text)
        if not qr["passed"]:
            issue_messages = [i["message"] for i in qr["issues"]]
            score = qr.get("score", 0.5)
            _emit(on_event, {"event_type": "workflow_step_quality_warning", "workflow_id": workflow_id, "step_id": step.step_id, "quality_score": score, "issues": issue_messages})
            if score < 0.3:
                raise ValueError(f"Quality gate failed for step '{step.step_id}' (score {score:.2f}): " + "; ".join(issue_messages[:3]))
            logger.warning("Step %s quality gate warning (score %.2f): %s", step.step_id, score, issue_messages)
    except ValueError:
        raise
    except Exception:
        pass


def _emit_step_kickoff_chat(step: WorkflowStep, step_inputs: dict[str, Any], tenant_id: str, run_id: str, on_event: Optional[Callable]) -> None:
    if step.step_type not in ("agent", "") or not run_id:
        return
    try:
        from api.services.agent.brain.team_chat import get_team_chat_service
        from api.services.agents.workflow_context import WorkflowRunContext

        roster = WorkflowRunContext(run_id).read("__workflow_agent_roster")
        if not isinstance(roster, list) or len(roster) < 2:
            return
        original_task = str(step_inputs.get("message") or step_inputs.get("task") or step.description or "").strip()
        if not original_task:
            return
        chat_svc = get_team_chat_service()
        conversation = chat_svc.start_conversation(run_id=run_id, topic=original_task, initiated_by=step.agent_id or step.step_id, step_id=step.step_id, on_event=on_event)
        chat_svc.kickoff_step(conversation=conversation, current_agent=str(step.agent_id or step.step_id or "").strip(), step_description=str(step.description or original_task).strip(), original_task=original_task, agents=roster, step_id=step.step_id, tenant_id=tenant_id, on_event=on_event)
    except Exception as exc:
        logger.debug("Step kickoff chat skipped: %s", exc)
