from __future__ import annotations

import logging
import time
from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent, utc_now
from api.services.agent.observability import get_agent_observability
from api.services.agent.planner import PlannedStep
from api.services.agent.middleware.integration import build_step_context

from api.services.agent.interaction_suggestion.emitter import maybe_emit_interaction_suggestion

_mw_logger = logging.getLogger(__name__)

from ..execution_trace import record_retry_trace
from ..handoff_state import handoff_pause_notice, is_handoff_paused
from ..models import ExecutionState, TaskPreparation
from ..role_contracts import resolve_owner_role_for_tool
from .failure import handle_step_failure
from .guards import (
    prepare_step_params,
    run_guard_checks,
    should_skip_step_for_workspace_logging,
)
from .success import _tool_surface_info, handle_step_success

if TYPE_CHECKING:
    from api.services.agent.brain import Brain

# Lazy-loaded chain-of-thought reasoner (avoids import cost when not used).
_cot_reasoner = None


def _get_cot_reasoner():
    """Lazy-load ChainOfThoughtReasoner to avoid circular imports."""
    global _cot_reasoner
    if _cot_reasoner is None:
        try:
            from api.services.agent.reasoning.chain_of_thought import ChainOfThoughtReasoner
            _cot_reasoner = ChainOfThoughtReasoner()
        except Exception as _cot_exc:
            _mw_logger.debug("cot_reasoner_init_failed error=%s", _cot_exc)
            _cot_reasoner = None
    return _cot_reasoner


def _extract_content_summary(result: Any) -> str:
    """Extract a human-readable content summary from any tool result shape.

    Handles:
    - ToolExecutionResult dataclass (.summary / .content attributes)
    - Workspace tool dicts (document_url, spreadsheet_url, updated_rows, values, etc.)
    - Generic dicts (summary, content, text keys)
    - Fallback: str(result)
    """
    if result is None:
        return ""
    # ToolExecutionResult (or any dataclass/object with .summary)
    if hasattr(result, "summary") and result.summary:
        base = str(result.summary)[:400]
        # Append content if it adds more detail
        content = str(getattr(result, "content", "") or "")
        if content and content not in base:
            base = f"{base} | {content[:200]}"
        return base[:600]
    if isinstance(result, dict):
        # Generic keys first
        for key in ("summary", "content", "text", "answer", "output"):
            val = result.get(key)
            if val:
                return str(val)[:600]
        # Workspace tool result keys — build a descriptive summary
        parts: list[str] = []
        if result.get("document_id") or result.get("doc_id"):
            doc_url = result.get("document_url") or result.get("doc_url") or ""
            parts.append(f"Doc created: {doc_url or result.get('document_id') or result.get('doc_id')}")
        if result.get("spreadsheet_id"):
            sheet_url = result.get("spreadsheet_url") or ""
            updated = result.get("updated_rows", "")
            parts.append(f"Sheet: {sheet_url or result.get('spreadsheet_id')} updated_rows={updated}")
        if result.get("values"):
            rows = result["values"]
            row_count = len(rows) if isinstance(rows, list) else 0
            parts.append(f"Read {row_count} row(s) from sheet")
        if result.get("file_id"):
            parts.append(f"Drive file: {result.get('file_id')}")
        if result.get("files") and isinstance(result["files"], list):
            parts.append(f"Drive search: {len(result['files'])} file(s) found")
        if result.get("deleted"):
            parts.append(f"Deleted file: {result.get('deleted')}")
        if parts:
            return " | ".join(parts)[:600]
        # Last resort: serialize non-empty dict keys
        return str({k: v for k, v in result.items() if v and k != "events"})[:600]
    return str(result)[:600]


def _make_brain_signal(
    *,
    step: PlannedStep,
    index: int,
    owner_role: str,
    status: str,
    elapsed: float,
    result: Any = None,
    exc: Exception | None = None,
) -> Any:
    """Build a BrainSignal from step execution results (lazy import to avoid circulars)."""
    from api.services.agent.brain import BrainSignal, StepOutcome
    content_summary = _extract_content_summary(result)
    outcome = StepOutcome(
        step_index=index,
        tool_id=step.tool_id,
        owner_role=owner_role,
        status=status,  # type: ignore[arg-type]
        content_summary=content_summary,
        evidence_count=1 if content_summary else 0,
        error_message=str(exc)[:200] if exc else "",
        duration_ms=int(elapsed * 1000),
    )
    return BrainSignal(source_role=owner_role, outcome=outcome)


# All tool IDs that make outbound HTTP calls and qualify for one transient-error retry.
_HTTP_RETRYABLE_TOOL_IDS = frozenset({
    "browser.playwright.inspect",
    "marketing.web_research",
    "web.extract.structured",
    "web.dataset.adapter",
    "browser.contact_form.send",
})

_TRANSIENT_ERROR_MARKERS = (
    "net::err_http2_protocol_error",
    "net::err_connection_reset",
    "net::err_connection_closed",
    "net::err_timed_out",
    "net::err_name_not_resolved",
    "navigation timeout",
    "read timeout",
    "connection timeout",
    "connectionerror",
    "timeout expired",
    "service unavailable",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway",
)


def _should_retry_transient_failure(
    *,
    step: PlannedStep,
    params: dict[str, Any],
    exc: Exception,
) -> bool:
    if step.tool_id not in _HTTP_RETRYABLE_TOOL_IDS:
        return False
    if bool(params.get("__retry_attempted")):
        return False
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_ERROR_MARKERS)


def execute_planned_steps(
    *,
    run_id: str,
    request: ChatRequest,
    access_context: Any,
    registry: Any,
    steps: list[PlannedStep],
    execution_prompt: str,
    deep_research_mode: bool,
    task_prep: TaskPreparation,
    state: ExecutionState,
    run_tool_live: Callable[..., Generator[dict[str, Any], None, Any]],
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
    brain: "Brain | None" = None,
) -> Generator[dict[str, Any], None, None]:
    step_cursor = 0
    display_step_index = 0
    active_role = " ".join(
        str(state.execution_context.settings.get("__active_execution_role") or "").split()
    ).strip().lower()
    while step_cursor < len(steps):
        if is_handoff_paused(settings=state.execution_context.settings):
            # Persist cursor so a resumed run restarts from this exact step, not step 0.
            state.execution_context.settings["__handoff_pause_step_cursor"] = step_cursor
            if not bool(state.execution_context.settings.get("__handoff_pause_emitted")):
                pause_notice = handoff_pause_notice(settings=state.execution_context.settings)
                pause_event = activity_event_factory(
                    event_type=str(pause_notice.get("event_type") or "handoff_paused"),
                    title=str(pause_notice.get("title") or "Execution paused for human verification"),
                    detail=str(pause_notice.get("detail") or "")[:200],
                    metadata=dict(pause_notice.get("metadata") or {}),
                )
                yield emit_event(pause_event)
                waiting_event = activity_event_factory(
                    event_type="agent.waiting",
                    title="Agent waiting for human verification",
                    detail=str(pause_notice.get("detail") or "")[:200],
                    metadata={
                        **dict(pause_notice.get("metadata") or {}),
                        "agent_event_type": "agent.waiting",
                    },
                )
                yield emit_event(waiting_event)
                state.execution_context.settings["__handoff_pause_emitted"] = True
            break
        step = steps[step_cursor]
        if should_skip_step_for_workspace_logging(state=state, step=step):
            step_cursor += 1
            continue

        display_step_index += 1
        index = display_step_index
        step_started = utc_now().isoformat()
        owner_role = resolve_owner_role_for_tool(step.tool_id)
        if active_role != owner_role:
            if active_role:
                handoff_event = activity_event_factory(
                    event_type="role_handoff",
                    title="Role handoff",
                    detail=f"{active_role} -> {owner_role}",
                    metadata={
                        "from_role": active_role,
                        "to_role": owner_role,
                        "owner_role": owner_role,
                        "step": index,
                        "tool_id": step.tool_id,
                    },
                )
                yield emit_event(handoff_event)
                agent_handoff_event = activity_event_factory(
                    event_type="agent.handoff",
                    title="Agent handoff",
                    detail=f"{active_role} -> {owner_role}",
                    metadata={
                        "agent_event_type": "agent.handoff",
                        "from_role": active_role,
                        "to_role": owner_role,
                        "owner_role": owner_role,
                        "step": index,
                        "tool_id": step.tool_id,
                    },
                )
                yield emit_event(agent_handoff_event)
            role_event = activity_event_factory(
                event_type="role_activated",
                title=f"Role active: {owner_role}",
                detail=step.title[:200],
                metadata={
                    "role": owner_role,
                    "owner_role": owner_role,
                    "step": index,
                    "tool_id": step.tool_id,
                },
            )
            yield emit_event(role_event)
            agent_resume_event = activity_event_factory(
                event_type="agent.resume",
                title=f"Agent resumed: {owner_role}",
                detail=step.title[:200],
                metadata={
                    "agent_event_type": "agent.resume",
                    "role": owner_role,
                    "owner_role": owner_role,
                    "step": index,
                    "tool_id": step.tool_id,
                },
            )
            yield emit_event(agent_resume_event)
            active_role = owner_role
            state.execution_context.settings["__active_execution_role"] = owner_role

        # Brain: emit forward-looking rationale before the step runs.
        if brain is not None:
            _rationale = brain.pre_step_rationale(step=step, step_index=display_step_index)
            if _rationale and _rationale != step.why_this_step:
                _rationale_event = activity_event_factory(
                    event_type="brain_rationale",
                    title="Why this step",
                    detail=_rationale[:400],
                    metadata={"tool_id": step.tool_id, "step": display_step_index},
                )
                yield emit_event(_rationale_event)

        # --- Chain-of-Thought: explicit reasoning before tool execution ---
        try:
            _cot = _get_cot_reasoner()
            if _cot is not None and brain is not None:
                _cot_step_dict = {
                    "tool_id": step.tool_id,
                    "title": step.title,
                    "params": step.params,
                    "why_this_step": step.why_this_step,
                }
                _cot_evidence = list(brain.state.evidence_pool) if hasattr(brain, "state") else []
                _cot_remaining = max(0, len(steps) - step_cursor - 1)
                _cot_goal = str(
                    getattr(brain.state, "user_message", "") if hasattr(brain, "state") else ""
                )[:300]
                _reasoning_chain = _cot.reason_before_action(
                    task_goal=_cot_goal,
                    current_step=_cot_step_dict,
                    evidence_so_far=_cot_evidence,
                    remaining_steps=_cot_remaining,
                )
                if _reasoning_chain.thoughts:
                    _cot_detail = " | ".join(_reasoning_chain.thoughts[:5])
                    if _reasoning_chain.conclusion:
                        _cot_detail += f" => {_reasoning_chain.conclusion}"
                    _cot_event = activity_event_factory(
                        event_type="brain_thinking",
                        title="Chain-of-thought reasoning",
                        detail=_cot_detail[:600],
                        metadata={
                            "tool_id": step.tool_id,
                            "step": display_step_index,
                            "confidence": _reasoning_chain.confidence,
                            "should_modify_params": _reasoning_chain.should_modify_params,
                            "reasoning_type": "chain_of_thought_pre_action",
                        },
                    )
                    yield emit_event(_cot_event)
        except Exception as _cot_exc:
            _mw_logger.debug("chain_of_thought.pre_action_failed error=%s", _cot_exc)

        event_family, scene_surface = _tool_surface_info(step.tool_id)
        queued_event = activity_event_factory(
            event_type="tool_queued",
            title=step.title,
            detail=step.tool_id,
            metadata={
                "tool_id": step.tool_id,
                "step": index,
                "event_family": event_family,
                "scene_surface": scene_surface,
            },
        )
        yield emit_event(queued_event)
        step_event = activity_event_factory(
            event_type="tool_started",
            title=step.title,
            detail=step.tool_id,
            metadata={
                "tool_id": step.tool_id,
                "step": index,
                "event_family": event_family,
                "scene_surface": scene_surface,
            },
        )
        yield emit_event(step_event)
        progress_event = activity_event_factory(
            event_type="tool_progress",
            title=step.title,
            detail="Tool execution in progress",
            metadata={
                "tool_id": step.tool_id,
                "step": index,
                "progress": 0.5,
                "event_family": event_family,
                "scene_surface": scene_surface,
            },
        )
        yield emit_event(progress_event)

        # Emit a pre-execution interaction hint so the UI can show an anticipatory
        # cursor/focus cue while the tool is running, not after it completes.
        # Uses a fresh per-step list so the cap resets for every step.
        _task_context = " ".join(
            str(
                task_prep.contract_objective
                or task_prep.rewritten_task
                or ""
            ).split()
        )[:120]
        _step_suggestions: list[Any] = []
        _pre_hints = maybe_emit_interaction_suggestion(
            tool_id=step.tool_id,
            step_title=step.title,
            step_index=index,
            total_steps=len(steps),
            step_why=step.why_this_step,
            step_params=step.params,
            task_context=_task_context,
            emit_event=emit_event,
            activity_event_factory=activity_event_factory,
            suggestions_emitted_this_step=_step_suggestions,
        )
        for _hint in _pre_hints:
            yield _hint

        params = prepare_step_params(step=step, access_context=access_context)
        guard_outcome = yield from run_guard_checks(
            run_id=run_id,
            request=request,
            task_prep=task_prep,
            state=state,
            registry=registry,
            steps=steps,
            step_cursor=step_cursor,
            index=index,
            step_started=step_started,
            step=step,
            params=params,
            emit_event=emit_event,
            activity_event_factory=activity_event_factory,
        )
        if guard_outcome.decision == "restart":
            continue
        if guard_outcome.decision == "skip":
            step_cursor += 1
            continue

        _step_halt = False

        # -- Middleware: build context and run before-hooks --
        _mw_pipeline = state.execution_context.settings.get("__middleware_pipeline")
        _mw_ctx = None
        _mw_active: list[Any] = []
        if _mw_pipeline is not None:
            try:
                _mw_ctx = build_step_context(
                    run_id=run_id,
                    tenant_id=state.execution_context.tenant_id,
                    user_id=state.execution_context.user_id,
                    step_index=index,
                    step_name=step.title,
                    tool_id=step.tool_id,
                    tool_params=guard_outcome.params,
                    depth=0,
                )
                _mw_active = [s for s in _mw_pipeline._stages if s.enabled]
                _mw_before_ran = 0
                for _mw_stage in _mw_active:
                    _mw_ctx = _mw_stage.before_step(_mw_ctx)
                    _mw_before_ran += 1
            except Exception as _mw_exc:
                _mw_logger.warning("Middleware before_step aborted: %s", _mw_exc)
                # On before-hook failure, run on_error for stages that already ran,
                # then fall through to direct execution (pipeline becomes no-op).
                if _mw_ctx is not None:
                    _mw_ctx.error = _mw_exc
                    for _prev in reversed(_mw_active[: _mw_before_ran]):
                        try:
                            _mw_ctx = _prev.on_error(_mw_ctx, _mw_exc)
                        except Exception:
                            pass
                _mw_ctx = None  # Disable after-hooks
                _mw_active = []

        tool_started_clock = time.perf_counter()
        try:
            result = yield from run_tool_live(
                step=step,
                step_index=index,
                prompt=execution_prompt,
                params=guard_outcome.params,
            )
            elapsed = time.perf_counter() - tool_started_clock

            # -- Middleware: run after-hooks on success --
            if _mw_ctx is not None:
                _mw_ctx.result = result
                _mw_ctx.duration_ms = elapsed * 1000
                for _mw_stage in reversed(_mw_active):
                    try:
                        _mw_ctx = _mw_stage.after_step(_mw_ctx)
                    except Exception as _mw_after_exc:
                        _mw_logger.warning("Middleware %s.after_step failed: %s", _mw_stage.name, _mw_after_exc)

            get_agent_observability().observe_tool_execution(
                tool_id=step.tool_id,
                status="success",
                duration_seconds=elapsed,
            )
            yield from handle_step_success(
                access_context=access_context,
                deep_research_mode=deep_research_mode,
                execution_prompt=execution_prompt,
                state=state,
                registry=registry,
                steps=steps,
                step_cursor=step_cursor,
                step=step,
                index=index,
                step_started=step_started,
                duration_seconds=elapsed,
                result=result,
                run_tool_live=run_tool_live,
                emit_event=emit_event,
                activity_event_factory=activity_event_factory,
            )
            if brain is not None:
                _directive = yield from brain.observe_step(
                    signal=_make_brain_signal(
                        step=step, index=index, owner_role=owner_role,
                        status="success", elapsed=elapsed, result=result,
                    ),
                    steps=steps,
                    emit_event=emit_event,
                    activity_event_factory=activity_event_factory,
                )
                if _directive.action == "halt":
                    _step_halt = True
        except Exception as exc:
            elapsed = time.perf_counter() - tool_started_clock

            # -- Middleware: run on_error hooks --
            if _mw_ctx is not None:
                _mw_ctx.error = exc
                _mw_ctx.duration_ms = elapsed * 1000
                for _mw_stage in reversed(_mw_active):
                    try:
                        _mw_ctx = _mw_stage.on_error(_mw_ctx, exc)
                    except Exception:
                        pass

            if _should_retry_transient_failure(
                step=step,
                params=guard_outcome.params,
                exc=exc,
            ):
                retry_trace = record_retry_trace(
                    state=state,
                    step_index=index,
                    tool_id=step.tool_id,
                    reason=str(exc),
                    status="started",
                )
                retry_event = activity_event_factory(
                    event_type="tool_progress",
                    title=step.title,
                    detail="Transient browser error detected; retrying once with reduced scope.",
                    metadata={
                        "tool_id": step.tool_id,
                        "step": index,
                        "retry": True,
                        "retry_trace": retry_trace,
                    },
                )
                yield emit_event(retry_event)
                retry_params = dict(guard_outcome.params)
                retry_params["__retry_attempted"] = True
                retry_params.setdefault("follow_same_domain_links", False)
                retry_started_clock = time.perf_counter()
                try:
                    retry_result = yield from run_tool_live(
                        step=step,
                        step_index=index,
                        prompt=execution_prompt,
                        params=retry_params,
                    )
                    retry_elapsed = time.perf_counter() - retry_started_clock
                    get_agent_observability().observe_tool_execution(
                        tool_id=step.tool_id,
                        status="success",
                        duration_seconds=retry_elapsed,
                    )
                    record_retry_trace(
                        state=state,
                        step_index=index,
                        tool_id=step.tool_id,
                        reason="retry completed successfully",
                        status="completed",
                    )
                    yield from handle_step_success(
                        access_context=access_context,
                        deep_research_mode=deep_research_mode,
                        execution_prompt=execution_prompt,
                        state=state,
                        registry=registry,
                        steps=steps,
                        step_cursor=step_cursor,
                        step=step,
                        index=index,
                        step_started=step_started,
                        duration_seconds=retry_elapsed,
                        result=retry_result,
                        run_tool_live=run_tool_live,
                        emit_event=emit_event,
                        activity_event_factory=activity_event_factory,
                    )
                    if brain is not None:
                        _directive = yield from brain.observe_step(
                            signal=_make_brain_signal(
                                step=step, index=index, owner_role=owner_role,
                                status="success", elapsed=retry_elapsed, result=retry_result,
                            ),
                            steps=steps,
                            emit_event=emit_event,
                            activity_event_factory=activity_event_factory,
                        )
                        if _directive.action == "halt":
                            break
                    step_cursor += 1
                    continue
                except Exception as retry_exc:
                    record_retry_trace(
                        state=state,
                        step_index=index,
                        tool_id=step.tool_id,
                        reason=str(retry_exc),
                        status="failed",
                    )
                    exc = retry_exc
                    elapsed = time.perf_counter() - retry_started_clock
            get_agent_observability().observe_tool_execution(
                tool_id=step.tool_id,
                status="failed",
                duration_seconds=elapsed,
            )
            yield from handle_step_failure(
                execution_prompt=execution_prompt,
                state=state,
                registry=registry,
                step=step,
                index=index,
                step_started=step_started,
                duration_seconds=elapsed,
                exc=exc,
                emit_event=emit_event,
                activity_event_factory=activity_event_factory,
            )
            # --- Chain-of-Thought: structured failure analysis ---
            try:
                _cot_fail = _get_cot_reasoner()
                if _cot_fail is not None:
                    _fail_step_dict = {
                        "tool_id": step.tool_id,
                        "title": step.title,
                        "params": step.params,
                        "why_this_step": step.why_this_step,
                    }
                    _fail_evidence = []
                    if brain is not None and hasattr(brain, "state"):
                        _fail_evidence = list(brain.state.evidence_pool)
                    _fail_tools: list[str] = []
                    try:
                        if hasattr(registry, "list_tool_ids"):
                            _fail_tools = list(registry.list_tool_ids())[:30]
                        elif hasattr(registry, "tools"):
                            _fail_tools = [
                                t.tool_id for t in list(registry.tools.values())[:30]
                            ]
                    except Exception:
                        pass
                    _recovery = _cot_fail.reason_after_failure(
                        failed_step=_fail_step_dict,
                        error=str(exc)[:400],
                        evidence_pool=_fail_evidence,
                        available_tools=_fail_tools,
                    )
                    if _recovery.analysis:
                        _recovery_detail = (
                            f"Root cause: {_recovery.root_cause}. "
                            f"{_recovery.analysis[:300]} "
                            f"Recommended: {_recovery.recommended_action}"
                        )
                        _recovery_event = activity_event_factory(
                            event_type="brain_thinking",
                            title="Failure analysis",
                            detail=_recovery_detail[:600],
                            metadata={
                                "tool_id": step.tool_id,
                                "step": index,
                                "root_cause": _recovery.root_cause[:120],
                                "recommended_action": _recovery.recommended_action,
                                "recovery_option_count": len(_recovery.recovery_options),
                                "reasoning_type": "chain_of_thought_failure_analysis",
                            },
                        )
                        yield emit_event(_recovery_event)
            except Exception as _cot_fail_exc:
                _mw_logger.debug("chain_of_thought.failure_analysis_failed error=%s", _cot_fail_exc)

            if brain is not None:
                _directive = yield from brain.observe_step(
                    signal=_make_brain_signal(
                        step=step, index=index, owner_role=owner_role,
                        status="failed", elapsed=elapsed, exc=exc,
                    ),
                    steps=steps,
                    emit_event=emit_event,
                    activity_event_factory=activity_event_factory,
                )
                if _directive.action == "halt":
                    _step_halt = True
        if _step_halt:
            break
        step_cursor += 1
