from __future__ import annotations

from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowStep

from .common import _looks_like_customer_facing_output, logger
from .review import _is_safe_integrated_output, _should_skip_dialogue_need_for_reviewed_output


def _normalize_dialogue_turn_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
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
    allowed = {"email", "sheet", "document", "api", "browser", "chat", "crm", "support", "commerce"}
    return normalized if normalized in allowed else ""


def _normalize_dialogue_scene_surface(value: Any, *, scene_family: str = "") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"email", "google_sheets", "google_docs", "api", "website", "system"}:
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
        return f"Collaboration style: {label}. Respond with the evidence, correction, or revision needed. Context: {reason_text}"
    if label:
        return f"Collaboration style: {label}. Respond clearly with concrete supporting detail."
    if reason_text:
        return f"Respond with concise, actionable input. Context: {reason_text}"
    return "Respond with concise, actionable teammate input."


def _run_dialogue_detection(
    step: WorkflowStep,
    output: str,
    tenant_id: str,
    run_id: str,
    on_event: Optional[Callable],
    run_agent_for_agent_fn: Optional[Callable[[str, str], str]] = None,
) -> str:
    try:
        import os
        if os.getenv("MAIA_DIALOGUE_ENABLED", "true").strip().lower() in ("false", "0", "no"):
            return output

        from api.services.agent.brain.dialogue_detector import (
            detect_dialogue_needs,
            evaluate_dialogue_follow_up,
            infer_dialogue_scene,
            propose_seed_dialogue_turn,
        )
        from api.services.agent.dialogue_turns import get_dialogue_service
        from api.services.agents.workflow_context import WorkflowRunContext

        run_ctx = WorkflowRunContext(run_id) if run_id else None
        available_agents = run_ctx.read("__workflow_agent_ids") if run_ctx else []
        available_roster = run_ctx.read("__workflow_agent_roster") if run_ctx else []
        if not isinstance(available_agents, list) or not available_agents:
            return output
        if not isinstance(available_roster, list):
            available_roster = []

        needs = detect_dialogue_needs(agent_output=output, current_agent=step.agent_id or step.step_id, available_agents=available_agents, agent_roster=available_roster, step_description=step.description, tenant_id=tenant_id)
        if not needs:
            seed_turn = propose_seed_dialogue_turn(agent_output=output, current_agent=step.agent_id or step.step_id, available_agents=available_agents, agent_roster=available_roster, step_description=step.description, tenant_id=tenant_id)
            if isinstance(seed_turn, dict) and seed_turn.get("question"):
                needs = [seed_turn]

        needs = [
            need for need in needs
            if not _should_skip_dialogue_need_for_reviewed_output(
                output=output,
                interaction_type=need.get("interaction_type", "question"),
                interaction_label=need.get("interaction_label", ""),
                operation_label=need.get("operation_label", ""),
                question=need.get("question", ""),
                reason=need.get("reason", ""),
            )
        ]
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
            request_text = f"{question}\n\nWhy this matters: {reason}" if reason else question
            if not scene_family or not scene_surface:
                inferred_scene = infer_dialogue_scene(current_agent=source_agent, target_agent=target, interaction_type=interaction_type, interaction_label=interaction_label, operation_label=operation_label, question=request_text, reason=reason, step_description=str(step.description or ""), source_output=str(output or ""), tenant_id=tenant_id)
                scene_family = scene_family or _normalize_dialogue_scene_family(inferred_scene.get("scene_family"))
                scene_surface = scene_surface or _normalize_dialogue_scene_surface(inferred_scene.get("scene_surface"), scene_family=scene_family)
                action = _dialogue_action_for_surface(scene_surface=scene_surface, scene_family=scene_family)
            prompt_preamble = _build_dialogue_prompt_preamble(interaction_label=interaction_label, reason=reason)
            response_turn_type = _derive_response_turn_type(interaction_type)

            if on_event:
                on_event({"event_type": "agent_dialogue_started", "title": f"{source_agent} needs input from {target}", "detail": request_text[:200], "data": {"from_agent": source_agent, "to_agent": target, "run_id": run_id, "turn_role": "request", "turn_type": interaction_type, "interaction_type": interaction_type, "interaction_label": interaction_label, "scene_family": scene_family, "scene_surface": scene_surface, "operation_label": operation_label or interaction_label, "action": action, "action_phase": "active", "action_status": "in_progress"}})

            answer = dialogue_svc.ask(run_id=run_id, from_agent=source_agent, to_agent=target, question=request_text, tenant_id=tenant_id, on_event=on_event, answer_fn=run_agent_for_agent_fn, ask_turn_type=interaction_type, answer_turn_type=response_turn_type, ask_turn_role="request", answer_turn_role="response", interaction_label=interaction_label, scene_family=scene_family, scene_surface=scene_surface, operation_label=operation_label, action=action, action_phase="active", action_status="in_progress", prompt_preamble=prompt_preamble)

            follow_up = evaluate_dialogue_follow_up(source_agent=source_agent, target_agent=target, interaction_type=interaction_type, initial_request=request_text, teammate_response=str(answer or ""), source_output=str(output or ""), tenant_id=tenant_id)
            if follow_up.get("requires_follow_up") and run_agent_for_agent_fn:
                follow_up_prompt = str(follow_up.get("follow_up_prompt", "")).strip()
                if follow_up_prompt:
                    follow_up_type = _normalize_dialogue_turn_type(follow_up.get("follow_up_type", interaction_type))
                    follow_up_label = str(follow_up.get("follow_up_label", "")).strip() or str(follow_up.get("reason", "")).strip() or interaction_label
                    answer = dialogue_svc.ask(run_id=run_id, from_agent=source_agent, to_agent=target, question=follow_up_prompt, tenant_id=tenant_id, on_event=on_event, answer_fn=run_agent_for_agent_fn, ask_turn_type=follow_up_type, answer_turn_type=_derive_response_turn_type(follow_up_type), ask_turn_role="request", answer_turn_role="response", interaction_label=follow_up_label, scene_family=scene_family, scene_surface=scene_surface, operation_label=operation_label, action=action, action_phase="active", action_status="in_progress", prompt_preamble=_build_dialogue_prompt_preamble(interaction_label=follow_up_label, reason=str(follow_up.get("reason", "")).strip()))

            integrated = False
            if run_agent_for_agent_fn:
                try:
                    integration_prompt = (
                        f"You are {source_agent}. You asked teammate {target}: {question}\n\n"
                        f"Teammate answer:\n{answer}\n\n"
                        f"Your current step output:\n{output[:3500]}\n\n"
                        "Revise your output to integrate valid teammate insights. If you disagree with a point, state why with evidence."
                    )
                    revised_text = str(run_agent_for_agent_fn(source_agent, integration_prompt) or "").strip()
                    if revised_text and _is_safe_integrated_output(output, revised_text):
                        output = revised_text
                        integrated = True
                        if on_event:
                            on_event({"event_type": "agent_dialogue_turn", "title": f"{source_agent} integrated teammate input", "detail": revised_text[:300], "stage": "execute", "status": "info", "data": {"run_id": run_id, "from_agent": source_agent, "to_agent": "team", "turn_type": "integration", "turn_role": "integration", "interaction_label": "integrated teammate feedback", "scene_family": scene_family, "scene_surface": scene_surface, "operation_label": operation_label or "Integrate teammate feedback", "action": action, "action_phase": "completed", "action_status": "ok", "message": revised_text[:1000]}})
                except Exception as exc:
                    logger.debug("Dialogue integration skipped: %s", exc)

            if not integrated:
                enrichments.append(f"[From {target}]: {answer}")
            if on_event:
                on_event({"event_type": "agent_dialogue_resolved", "title": f"Dialogue resolved: {source_agent} -- {target}", "detail": str(answer or "")[:200], "data": {"from_agent": target, "to_agent": source_agent, "run_id": run_id, "turn_role": "response", "scene_family": scene_family, "scene_surface": scene_surface, "operation_label": operation_label or interaction_label, "action": action, "action_phase": "completed", "action_status": "ok"}})

        if enrichments and not _looks_like_customer_facing_output(step, output):
            output = f"{output}\n\n-- Additional context from team dialogue --\n" + "\n".join(enrichments)
        return output
    except Exception as exc:
        logger.debug("Dialogue detection skipped: %s", exc)
        return output
