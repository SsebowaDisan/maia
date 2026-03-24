from __future__ import annotations

import time
from typing import Any, Optional

from api.schemas.workflow_definition import WorkflowDefinitionSchema, WorkflowStep
from .common import _clean_stage_topic, _format_inputs, _step_tool_ids, _RETRY_BASE_DELAY, logger


def _record_failure_lesson(tenant_id: str, step: WorkflowStep, error: str, run_id: str) -> None:
    try:
        from api.services.agent.reasoning.evolution_store import EvolutionStore
        EvolutionStore(tenant_id=tenant_id).record_failure_lesson(step_id=step.step_id, error=error, run_id=run_id)
    except Exception:
        pass


def _ensure_supervisor_in_roster(workflow_agent_roster: list[dict[str, str]], *, workflow: WorkflowDefinitionSchema) -> list[dict[str, str]]:
    if len(workflow_agent_roster) < 3:
        return workflow_agent_roster
    roles = {" ".join(str(row.get("role") or "").strip().lower().split()) for row in workflow_agent_roster}
    if any("supervisor" in role or role in {"team lead", "lead"} for role in roles):
        return workflow_agent_roster
    supervisor_row = {
        "id": "supervisor",
        "agent_id": "supervisor",
        "name": "Supervisor",
        "role": "supervisor",
        "step_id": "",
        "step_description": str(workflow.description or workflow.name or "").strip() or "Resolve ambiguity, challenge weak evidence, and decide when work is ready to move.",
    }
    return [supervisor_row, *workflow_agent_roster]


def _run_step_with_retry(
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    workflow_id: str,
    run_id: str,
    on_event: Optional[Any] = None,
    step_timeout_s: int | None = None,
    ops: Any | None = None,
) -> Any:
    ops._validate_stage_contract(step, "input", step_inputs, workflow_id, on_event)
    last_exc: Exception | None = None
    max_attempts = 1 + step.max_retries
    step_deadline_ts = time.monotonic() + max(30, int(step_timeout_s or 0)) - 20.0 if step_timeout_s else None

    for attempt in range(1, max_attempts + 1):
        try:
            step_on_event = on_event
            direct_delivery_candidate = ops._is_direct_delivery_candidate(step, step_inputs)
            grounded_email_draft_candidate = ops._is_grounded_email_draft_candidate(step, step_inputs)
            if attempt == 1:
                ops._emit_step_kickoff_chat(step, step_inputs, tenant_id, run_id, on_event)
                try:
                    from api.services.agent.brain.action_chat import StepActionChatBridge
                    from api.services.agents.workflow_context import WorkflowRunContext
                    roster = WorkflowRunContext(run_id).read("__workflow_agent_roster")
                    original_task = str(step_inputs.get("message") or step_inputs.get("task") or step.description or "").strip()
                    if isinstance(roster, list) and len(roster) > 1 and original_task:
                        bridge = StepActionChatBridge(run_id=run_id, step_id=step.step_id, agent_id=str(step.agent_id or step.step_id or "").strip(), step_description=str(step.description or "").strip(), original_task=original_task, agents=roster, tenant_id=tenant_id, on_event=on_event)

                        def _step_event_proxy(event: dict[str, Any]) -> None:
                            if on_event:
                                on_event(event)
                            try:
                                bridge.observe(event)
                            except Exception as exc:
                                logger.debug("Action chat bridge skipped event: %s", exc)

                        step_on_event = _step_event_proxy
                except Exception as exc:
                    logger.debug("Action chat bridge unavailable: %s", exc)
            result = ops._dispatch_step(step, step_inputs, tenant_id, run_id, step_on_event)
            ops._validate_stage_contract(step, "output", result if isinstance(result, dict) else {}, workflow_id, on_event)
            if direct_delivery_candidate or grounded_email_draft_candidate:
                return result
            ops._run_quality_gate(step, result, workflow_id, on_event)
            result = ops._run_brain_review(step, result, step_inputs, tenant_id, run_id, on_event, step_deadline_ts=step_deadline_ts)
            return ops._compact_research_brief_output(step=step, step_inputs=step_inputs, result=result, tenant_id=tenant_id)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning("Step %s attempt %d/%d failed (%s) - retrying in %.1fs", step.step_id, attempt, max_attempts, exc, delay)
                if on_event:
                    on_event({"event_type": "workflow_step_retrying", "workflow_id": workflow_id, "step_id": step.step_id, "attempt": attempt, "max_attempts": max_attempts, "delay_s": delay, "error": str(exc)[:500]})
                time.sleep(delay)

    if last_exc is None:
        last_exc = RuntimeError(f"Step '{step.step_id}' failed with unknown error")
    _record_failure_lesson(tenant_id, step, str(last_exc)[:300], run_id)
    try:
        from api.services.workflows.dead_letter import record_dead_letter
        record_dead_letter(tenant_id=tenant_id, run_id=run_id, workflow_id=workflow_id, step_id=step.step_id, error=str(last_exc), inputs=step_inputs, attempt=max_attempts, step_type=step.step_type)
    except Exception as exc:
        logger.error("Failed to record dead-letter for step %s: %s", step.step_id, exc)
    raise last_exc


def _dispatch_step(
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str,
    on_event: Optional[Any] = None,
    ops: Any | None = None,
) -> Any:
    direct_delivery_candidate = False
    grounded_email_draft_candidate = False
    if step.step_type == "agent" or not step.step_type:
        direct_delivery_candidate = ops._is_direct_delivery_candidate(step, step_inputs)
        grounded_email_draft_candidate = ops._is_grounded_email_draft_candidate(step, step_inputs)

    try:
        from api.services.agent.approval_workflows import get_approval_service
        service = get_approval_service()
        raw_tool_ids = list(step.step_config.get("tool_ids") or []) if isinstance(step.step_config, dict) else []
        approval_candidates = ["mailer.report_send"] if direct_delivery_candidate else raw_tool_ids
        tool_ids = [t for t in approval_candidates if service.requires_approval(t, tenant_id)]
        if tool_ids:
            gate = service.create_gate(run_id=run_id, tool_id=tool_ids[0], params=step_inputs, connector_id=step.step_config.get("connector_id", ""))
            import time as _approval_time
            deadline = _approval_time.time() + 300
            while _approval_time.time() < deadline:
                pending = service.list_pending(run_id=run_id)
                if not any(g["gate_id"] == gate.gate_id for g in pending):
                    break
                _approval_time.sleep(2)
            if gate.status == "rejected":
                raise RuntimeError(f"Step '{step.step_id}' blocked: approval rejected for {tool_ids[0]}")
            if gate.status == "pending":
                raise RuntimeError(f"Step '{step.step_id}' blocked: approval timed out for {tool_ids[0]}")
            if gate.status == "approved" and gate.edited_params:
                step_inputs = {**step_inputs, **gate.edited_params}
    except RuntimeError:
        raise
    except Exception:
        pass

    if step.step_type == "agent" or not step.step_type:
        if direct_delivery_candidate:
            direct_delivery_result = ops._run_direct_delivery_step(step=step, step_inputs=step_inputs, tenant_id=tenant_id, run_id=run_id, agent_id=step.agent_id, on_event=on_event)
            if direct_delivery_result is not None:
                return direct_delivery_result
        if grounded_email_draft_candidate:
            return ops._run_grounded_email_draft_step(step=step, step_inputs=step_inputs, tenant_id=tenant_id, run_id=run_id, on_event=on_event)
        return ops._run_agent_step(step.agent_id, step_inputs, tenant_id, run_id=run_id, on_event=on_event, step=step)

    from api.services.workflows.nodes import get_handler
    handler = get_handler(step.step_type)
    if handler is None:
        raise ValueError(f"No handler registered for step_type '{step.step_type}'")
    return handler(step, step_inputs, on_event)


def _run_agent_step(
    agent_id: str,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str = "",
    on_event: Optional[Any] = None,
    step: WorkflowStep | None = None,
    ops: Any | None = None,
) -> Any:
    from api.services.agents.definition_store import get_agent, load_schema
    from api.services.agents.runner import run_agent_task

    record = get_agent(tenant_id, agent_id)
    if not record:
        raise ValueError(f"Agent '{agent_id}' not found in tenant '{tenant_id}'.")
    schema = load_schema(record)

    system_prompt = ops._inject_evolution_overlay(tenant_id, agent_id, schema.system_prompt or "")
    handoff_context = step_inputs.pop("__handoff_context", None)
    if handoff_context and isinstance(handoff_context, str):
        system_prompt = f"{system_prompt}\n\n{handoff_context}" if system_prompt else handoff_context

    task = step_inputs.get("message") or step_inputs.get("task") or f"Execute your task with the following context:\n{_format_inputs(step_inputs)}"
    query_hint = ""
    if step is not None:
        step_objective = str(step.description or "").strip()
        raw_step_tools = step.step_config.get("tool_ids") if isinstance(step.step_config, dict) and isinstance(step.step_config.get("tool_ids"), list) else []
        step_tool_ids = [str(tool_id).strip() for tool_id in raw_step_tools if str(tool_id).strip()]
        step_tool_set = {tool_id.lower() for tool_id in step_tool_ids}
        query_hint = " ".join(str(step_inputs.get("query") or step_inputs.get("topic") or "").split()).strip()
        supporting_inputs = {key: value for key, value in step_inputs.items() if key not in {"message", "task"} and value not in (None, "", [], {})}
        scoped_parts: list[str] = []
        if step_objective:
            scoped_parts.append("You are executing one workflow stage, not the entire user request.\n" f"Current stage objective:\n{step_objective}")
        if query_hint and step_tool_set.intersection({"marketing.web_research", "web.extract.structured", "browser.playwright.inspect"}):
            scoped_parts.append("Primary research topic:\n" f"{query_hint}\n\nUse this topic as the basis for search queries and source selection. Treat the broader stage objective as synthesis/output guidance, not as a literal search query.")
        scoped_parts.append("Stage completion rule:\nFinish only this stage and produce the handoff artifact needed by the next stage. Do not draft the final response, do not perform downstream delivery actions, and do not reopen completed stages unless the current stage explicitly requires it.")
        if supporting_inputs:
            scoped_parts.append("Available context and previous outputs:\n" f"{_format_inputs(supporting_inputs)}")
        if scoped_parts:
            task = "\n\n".join(scoped_parts)

    def _should_allow_report_synthesis(*, allowed: list[str] | None, explicit_step_scope: bool) -> bool:
        if explicit_step_scope or allowed is None:
            return False
        allowed_set = {str(tool_id).strip() for tool_id in allowed if str(tool_id).strip()}
        if "report.generate" in allowed_set or allowed_set.intersection({"gmail.draft", "gmail.send", "email.draft", "email.send", "mailer.report_send"}):
            return False
        if not allowed_set.intersection({"marketing.web_research", "web.extract.structured", "web.dataset.adapter", "browser.playwright.inspect", "documents.highlight.extract", "analytics.ga4.report", "analytics.ga4.full_report", "business.ga4_kpi_sheet_report"}):
            return False
        return True

    schema_tool_ids = [str(tool_id).strip() for tool_id in list(getattr(schema, "tools", []) or []) if str(tool_id).strip()] if getattr(schema, "tools", None) is not None else []
    step_tool_ids: list[str] | None = None
    if step is not None and isinstance(step.step_config, dict) and "tool_ids" in step.step_config:
        raw_step_tools = step.step_config.get("tool_ids")
        step_tool_ids = [str(tool_id).strip() for tool_id in raw_step_tools if str(tool_id).strip()] if isinstance(raw_step_tools, list) else []

    if step_tool_ids is not None:
        if schema_tool_ids:
            schema_tool_set = set(schema_tool_ids)
            allowed_tool_ids = [tool_id for tool_id in step_tool_ids if tool_id in schema_tool_set] or list(step_tool_ids)
        else:
            allowed_tool_ids = list(step_tool_ids)
    else:
        allowed_tool_ids = list(schema_tool_ids) if schema_tool_ids else None
    if _should_allow_report_synthesis(allowed=allowed_tool_ids, explicit_step_scope=step_tool_ids is not None):
        allowed_tool_ids = list(allowed_tool_ids or [])
        allowed_tool_ids.append("report.generate")

    settings_overrides: dict[str, Any] = {}
    if query_hint:
        settings_overrides["__workflow_stage_primary_topic"] = _clean_stage_topic(query_hint)
        settings_overrides["__research_search_terms"] = [_clean_stage_topic(query_hint)]

    result_parts: list[str] = []
    for chunk in run_agent_task(task, tenant_id=tenant_id, run_id=run_id or None, system_prompt=system_prompt or None, allowed_tool_ids=allowed_tool_ids, max_tool_calls=getattr(schema, "max_tool_calls_per_run", None), agent_id=agent_id, settings_overrides=settings_overrides or None):
        text = chunk.get("text") or chunk.get("content") or chunk.get("delta") or ""
        if text:
            result_parts.append(str(text))
        if on_event:
            if isinstance(chunk, dict) and str(chunk.get("type") or "").strip().lower() == "activity" and isinstance(chunk.get("event"), dict):
                event_payload = {**chunk["event"], "step_agent_id": agent_id}
                normalized_event = ops._normalize_child_activity_event(event_payload, parent_run_id=run_id, step_agent_id=agent_id) if run_id else event_payload
                if run_id:
                    ops._persist_parent_activity_event(normalized_event, parent_run_id=run_id)
                on_event(normalized_event)
            elif isinstance(chunk, dict) and str(chunk.get("event_type") or "").strip():
                event_payload = {**chunk, "step_agent_id": agent_id}
                normalized_event = ops._normalize_child_activity_event(event_payload, parent_run_id=run_id, step_agent_id=agent_id) if run_id else event_payload
                if run_id and str(normalized_event.get("event_type") or "").strip():
                    ops._persist_parent_activity_event(normalized_event, parent_run_id=run_id)
                on_event(normalized_event)

    raw_result = ops._verify_and_clean_citations("".join(result_parts), tenant_id)
    if run_id:
        raw_result = ops._append_activity_citation_section(raw_result, run_id=run_id, step_agent_id=agent_id)
    return raw_result


def _inject_evolution_overlay(tenant_id: str, agent_id: str, system_prompt: str) -> str:
    try:
        from api.services.agent.reasoning.evolution_store import EvolutionStore
        overlay = EvolutionStore(tenant_id=tenant_id).get_prompt_overlay(stage=agent_id, max_lessons=5)
        if overlay:
            return f"{system_prompt}\n\n{overlay}" if system_prompt else overlay
    except Exception:
        pass
    return system_prompt


def _verify_and_clean_citations(text: str, tenant_id: str) -> str:
    if not text or len(text) < 100:
        return text
    try:
        from api.services.agent.reasoning.citation_verify import strip_hallucinated_citations, verify_citations
        filenames: list[str] = []
        try:
            from api.context import get_context
            from ktem.db.engine import engine
            from sqlmodel import Session, select
            ctx = get_context()
            index = ctx.get_index()
            Source = index._resources.get("Source")
            if Source:
                with Session(engine) as session:
                    filenames = [str(r) for r in session.exec(select(Source.name)).all() if r]
        except Exception:
            pass
        results = verify_citations(text, uploaded_filenames=filenames)
        hallucinated = [r for r in results if r["status"] == "hallucinated"] if results else []
        if hallucinated:
            logger.info("Stripping %d hallucinated citations from agent output", len(hallucinated))
            return strip_hallucinated_citations(text, results)
    except Exception:
        pass
    return text


def _inject_handoff_context(
    workflow: Any,
    step: Any,
    step_inputs: dict[str, Any],
    outputs: dict[str, Any],
    run_id: str,
    on_event: Optional[Callable] = None,
) -> None:
    if step.step_type not in ("agent", ""):
        return
    try:
        from api.services.agent.handoff_manager import build_handoff_context
        incoming_edges = [e for e in workflow.edges if e.to_step == step.step_id]
        if not incoming_edges:
            return
        contexts: list[Any] = []
        seen_predecessors: set[str] = set()
        for edge in incoming_edges:
            prev_step_id = str(getattr(edge, "from_step", "") or "").strip()
            if not prev_step_id or prev_step_id in seen_predecessors:
                continue
            seen_predecessors.add(prev_step_id)
            prev_step = workflow.get_step(prev_step_id)
            if not prev_step:
                continue
            prev_output = str(outputs.get(prev_step.output_key, "")).strip() or (f"Completed step {prev_step_id}: {str(getattr(prev_step, 'description', '') or '').strip()}" or f"Completed step {prev_step_id}.")
            contexts.append(build_handoff_context(from_agent=prev_step.agent_id or prev_step_id, to_agent=step.agent_id or step.step_id, from_step_id=prev_step_id, to_step_id=step.step_id, previous_output=prev_output, step_description=step.description, run_id=run_id))
        if not contexts:
            return
        step_inputs["__handoff_context"] = contexts[0].to_prompt_context() if len(contexts) == 1 else ("You are receiving handoff context from multiple teammates.\n\n" + "\n\n".join(ctx.to_prompt_context() for ctx in contexts[-4:]))
        for context in contexts:
            if on_event:
                on_event({"event_type": "agent_handoff", "title": f"{context.from_agent} -> {context.to_agent}", "detail": context.summary[:220], "stage": "execute", "status": "info", "data": {**context.to_dict(), "run_id": run_id, "from_agent": context.from_agent, "to_agent": context.to_agent, "scene_family": "api", "scene_surface": "system", "operation_label": "Handoff context transfer", "action": "handoff", "action_phase": "completed", "action_status": "ok"}})
    except Exception:
        pass


def _resolve_inputs(input_mapping: dict[str, str], outputs: dict[str, Any], ctx: Any | None = None) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for param, source in input_mapping.items():
        if source.startswith("literal:"):
            resolved[param] = source[len("literal:"):]
        elif source.startswith("context:") and ctx is not None:
            resolved[param] = ctx.read(source[len("context:"):])
        else:
            resolved[param] = outputs.get(source, "")
    return resolved
