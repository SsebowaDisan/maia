"""Brain Review Loop — reviews each workflow step output before proceeding.

The Brain sits between workflow steps (not within a single agent).
After each agent completes its step, the Brain:
  1. Reviews the output against the original task and quality standards
  2. Decides: proceed, revise, question, or escalate
  3. If revise: sends specific feedback, the agent re-runs
  4. If question: asks the agent, gets an answer, re-reviews
  5. Max 3 rounds per step to prevent infinite loops

This extends the existing Brain (brain.py) which works within a single
agent turn. This review loop works across agents in a workflow team.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

MAX_REVIEW_ROUNDS = 3

ReviewDecision = str  # "proceed" | "revise" | "question" | "escalate"


def brain_review(
    *,
    agent_id: str,
    step_id: str,
    step_output: str,
    original_task: str,
    step_description: str = "",
    quality_score: float = 1.0,
    run_id: str = "",
    tenant_id: str = "",
    on_event: Optional[Callable] = None,
) -> dict[str, Any]:
    """Review a workflow step's output and decide what to do next.

    Returns: { decision, reasoning, feedback, question, confidence }
    """
    _emit(on_event, {
        "event_type": "brain_review_started",
        "title": f"Brain reviewing {agent_id}'s work",
        "detail": f"Step: {step_id}",
        "stage": "execute", "status": "running",
        "data": {
            "agent_id": agent_id, "step_id": step_id, "run_id": run_id,
            "scene_family": "api", "from_agent": "brain", "to_agent": agent_id,
        },
    })

    # Build the review prompt
    from .review_prompts import build_review_prompt, parse_review_response
    prompt = build_review_prompt(
        agent_id=agent_id,
        step_output=step_output,
        original_task=original_task,
        step_description=step_description,
        quality_score=quality_score,
    )

    # Call the LLM for the review decision (with timeout — don't hang the workflow)
    try:
        import concurrent.futures
        from api.services.agents.runner import run_agent_task

        def _review_call() -> str:
            result_parts: list[str] = []
            for chunk in run_agent_task(
                prompt["user"],
                tenant_id=tenant_id,
                system_prompt=prompt["system"],
                max_tool_calls=0,
            ):
                text = chunk.get("text") or chunk.get("content") or ""
                if text:
                    result_parts.append(str(text))
            return "".join(result_parts)

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(_review_call)
        try:
            raw_response = future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    except Exception as exc:
        logger.warning("Brain review LLM call failed or timed out: %s", exc)
        raw_response = '{"decision": "proceed", "reasoning": "Review unavailable", "confidence": 0.5}'

    decision = parse_review_response(raw_response)

    # Record in collaboration log
    try:
        from api.services.agent.collaboration_logs import get_collaboration_service
        svc = get_collaboration_service()
        if decision["decision"] == "revise":
            svc.record(run_id=run_id, from_agent="brain", to_agent=agent_id,
                       message=f"Revision requested: {decision.get('feedback', '')}", entry_type="disagreement")
        elif decision["decision"] == "question":
            svc.record(run_id=run_id, from_agent="brain", to_agent=agent_id,
                       message=decision.get("question", ""), entry_type="question")
        elif decision["decision"] == "proceed":
            svc.record(run_id=run_id, from_agent="brain", to_agent=agent_id,
                       message=f"Approved: {decision.get('reasoning', 'Output meets standards')}", entry_type="message")
    except Exception:
        pass

    _emit(on_event, {
        "event_type": "brain_review_decision",
        "title": f"Brain: {decision['decision']} for {agent_id}",
        "detail": decision.get("reasoning", "")[:300],
        "stage": "execute",
        "status": "completed" if decision["decision"] == "proceed" else "waiting",
        "data": {
            **decision, "agent_id": agent_id, "step_id": step_id, "run_id": run_id,
            "from_agent": "brain", "to_agent": agent_id,
        },
    })

    return decision


def brain_review_loop(
    *,
    agent_id: str,
    step_id: str,
    step_description: str,
    original_task: str,
    initial_output: str,
    run_id: str = "",
    tenant_id: str = "",
    on_event: Optional[Callable] = None,
    run_agent_fn: Optional[Callable] = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Run the full Brain review loop for a step.

    Returns: (final_output, review_history)
    """
    output = initial_output
    history: list[dict[str, Any]] = []

    for round_num in range(1, MAX_REVIEW_ROUNDS + 1):
        # Get quality score
        quality_score = 1.0
        try:
            from api.services.agent.reasoning.quality_gate import check_output_quality
            qr = check_output_quality(output)
            quality_score = qr.get("score", 1.0)
        except Exception:
            pass

        decision = brain_review(
            agent_id=agent_id, step_id=step_id, step_output=output,
            original_task=original_task, step_description=step_description,
            quality_score=quality_score, run_id=run_id, tenant_id=tenant_id,
            on_event=on_event,
        )
        decision["round"] = round_num
        history.append(decision)

        if decision["decision"] == "proceed":
            break

        if decision["decision"] == "revise" and run_agent_fn:
            feedback = decision.get("feedback", "Please improve your output.")
            revision_prompt = (
                f"REVISION REQUESTED (round {round_num}/{MAX_REVIEW_ROUNDS}):\n"
                f"{feedback}\n\n"
                f"Your previous output:\n{output[:2000]}\n\n"
                f"Please address the feedback and resubmit an improved version."
            )
            _emit(on_event, {
                "event_type": "brain_revision_requested",
                "title": f"Brain → {agent_id}: Revision round {round_num}",
                "detail": feedback[:300],
                "stage": "execute", "status": "running",
                "data": {"round": round_num, "feedback": feedback,
                         "from_agent": "brain", "to_agent": agent_id, "run_id": run_id},
            })
            try:
                output = run_agent_fn(revision_prompt)
            except Exception as exc:
                logger.warning("Revision run failed: %s", exc)
                break

        elif decision["decision"] == "question" and run_agent_fn:
            question = decision.get("question", "Can you clarify your output?")
            _emit(on_event, {
                "event_type": "brain_question",
                "title": f"Brain → {agent_id}: Question",
                "detail": question[:300],
                "stage": "execute", "status": "running",
                "data": {"question": question, "from_agent": "brain",
                         "to_agent": agent_id, "run_id": run_id},
            })
            try:
                answer = run_agent_fn(f"The Brain asks: {question}\n\nYour previous output:\n{output[:1500]}\n\nPlease answer the question.")
                # Record the answer
                try:
                    from api.services.agent.collaboration_logs import get_collaboration_service
                    get_collaboration_service().record(
                        run_id=run_id, from_agent=agent_id, to_agent="brain",
                        message=answer[:500], entry_type="response",
                    )
                except Exception:
                    pass
                _emit(on_event, {
                    "event_type": "brain_answer_received",
                    "title": f"{agent_id} → Brain: Response",
                    "detail": answer[:300],
                    "stage": "execute", "status": "info",
                    "data": {"answer": answer[:500], "from_agent": agent_id,
                             "to_agent": "brain", "run_id": run_id},
                })
                # Brain re-reviews with the answer in context
                output = f"{output}\n\n[Additional context from follow-up question]\nQ: {question}\nA: {answer}"
            except Exception:
                break
        else:
            break

    return output, history


def _emit(on_event: Optional[Callable], event: dict[str, Any]) -> None:
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass
    # Also publish to live events broker
    try:
        from api.services.agent.live_events import get_live_event_broker
        get_live_event_broker().publish(
            user_id="", run_id=event.get("data", {}).get("run_id", ""),
            event=event,
        )
    except Exception:
        pass
