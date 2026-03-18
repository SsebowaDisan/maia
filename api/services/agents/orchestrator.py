"""B2-05 — Multi-agent orchestrator (delegation layer).

Responsibility: extend the existing company_agent orchestrator to support
sub-agent delegation.  An orchestrator can call ``delegate_to_agent`` which
runs a child agent and returns its result.

Max delegation depth is enforced from the parent agent's config.
Each delegation emits activity events.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MAX_DEPTH = 3


class DelegationDepthError(Exception):
    pass


def delegate_to_agent(
    parent_agent_id: str,
    child_agent_id: str,
    task: str,
    context: dict[str, Any],
    *,
    tenant_id: str,
    run_id: str,
    current_depth: int = 0,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    on_event: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """Run a child agent as a sub-task and return its result.

    Args:
        parent_agent_id: ID of the delegating agent.
        child_agent_id: ID of the agent to delegate to.
        task: The natural-language task string for the child agent.
        context: Key-value context to inject into the child run.
        tenant_id: Active tenant.
        run_id: Parent run identifier (child gets a derived run_id).
        current_depth: How many delegation levels deep we already are.
        max_depth: Maximum depth before raising DelegationDepthError.
        on_event: Optional callback for activity events.

    Returns:
        dict with keys: ``success``, ``result``, ``child_run_id``, ``agent_id``.
    """
    if current_depth >= max_depth:
        raise DelegationDepthError(
            f"Delegation depth limit ({max_depth}) reached. "
            f"Parent: {parent_agent_id}, attempted child: {child_agent_id}."
        )

    child_run_id = f"{run_id}.{current_depth + 1}.{uuid.uuid4().hex[:8]}"

    _emit(on_event, {
        "event_type": "agent_delegated",
        "parent_agent_id": parent_agent_id,
        "child_agent_id": child_agent_id,
        "child_run_id": child_run_id,
        "task_preview": task[:200],
        "depth": current_depth + 1,
    })

    logger.info(
        "Delegating to agent '%s' (depth=%d, child_run_id=%s)",
        child_agent_id,
        current_depth + 1,
        child_run_id,
    )

    try:
        result = _run_child_agent(
            child_agent_id=child_agent_id,
            task=task,
            context=context,
            tenant_id=tenant_id,
            child_run_id=child_run_id,
            depth=current_depth + 1,
            max_depth=max_depth,
            on_event=on_event,
        )
        _emit(on_event, {
            "event_type": "agent_delegation_completed",
            "child_agent_id": child_agent_id,
            "child_run_id": child_run_id,
            "success": True,
        })
        return {"success": True, "result": result, "child_run_id": child_run_id, "agent_id": child_agent_id}

    except Exception as exc:
        logger.error("Child agent '%s' failed: %s", child_agent_id, exc, exc_info=True)
        _emit(on_event, {
            "event_type": "agent_delegation_failed",
            "child_agent_id": child_agent_id,
            "child_run_id": child_run_id,
            "error": str(exc)[:300],
        })
        return {
            "success": False,
            "result": None,
            "child_run_id": child_run_id,
            "agent_id": child_agent_id,
            "error": str(exc)[:300],
        }


def _run_child_agent(
    *,
    child_agent_id: str,
    task: str,
    context: dict[str, Any],
    tenant_id: str,
    child_run_id: str,
    depth: int,
    max_depth: int,
    on_event: Optional[Callable[[dict[str, Any]], None]],
) -> Any:
    """Actually run the child agent.  Delegates to the agent execution service."""
    from api.services.agents.definition_store import get_agent, load_schema

    record = get_agent(tenant_id, child_agent_id)
    if not record:
        raise ValueError(f"Child agent '{child_agent_id}' not found in tenant '{tenant_id}'.")

    schema = load_schema(record)

    # Build a minimal ChatRequest-like payload and run through the existing orchestrator
    # so we reuse all existing tool calling, memory, and streaming infrastructure.
    from api.services.agents.runner import run_agent_task

    result_parts: list[str] = []

    system_prompt = (schema.system_prompt or "") + (
        f"\n\nCONTEXT:\n{_format_context(context)}" if context else ""
    )

    # Collect streamed output into result
    for chunk in run_agent_task(
        task,
        tenant_id=tenant_id,
        run_id=child_run_id,
        system_prompt=system_prompt or None,
    ):
        text = chunk.get("text") or chunk.get("content") or ""
        if text:
            result_parts.append(str(text))
        if on_event:
            on_event({**chunk, "child_run_id": child_run_id, "depth": depth})

    return "".join(result_parts)


def _emit(on_event: Optional[Callable], event: dict[str, Any]) -> None:
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass


def _format_context(context: dict[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in context.items())


# ── Multi-agent consensus delegation (Innovation #9) ─────────────────────────

def delegate_with_consensus(
    task: str,
    agent_ids: list[str],
    context: dict[str, Any],
    *,
    tenant_id: str,
    run_id: str | None = None,
    on_event: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """Delegate the same task to multiple agents and return the consensus answer.

    Uses ConsensusEngine to gather proposals in parallel, evaluate agreement,
    and synthesise or arbitrate the best result.

    Returns:
        dict with keys: ``success``, ``result``, ``consensus_type``,
        ``agreement_score``, ``dissenting_views``.
    """
    try:
        from api.services.agent.coordination.consensus import ConsensusEngine

        engine = ConsensusEngine(
            tenant_id=tenant_id,
            run_id=run_id or str(uuid.uuid4()),
            on_event=on_event,
        )

        proposals = engine.gather_proposals(task, agent_ids, context)
        if not proposals:
            return {
                "success": False,
                "result": None,
                "error": "No agent proposals were collected.",
                "consensus_type": "no_consensus",
                "agreement_score": 0.0,
            }

        consensus = engine.evaluate_proposals(proposals)

        # If no_consensus, attempt arbitration
        if consensus.consensus_type == "no_consensus" and len(proposals) > 1:
            winner = engine.arbitrate(proposals, "accuracy, completeness, evidence quality")
            return {
                "success": True,
                "result": winner.response,
                "consensus_type": "arbitrated",
                "agreement_score": consensus.agreement_score,
                "dissenting_views": consensus.dissenting_views,
                "winning_agent": winner.agent_id,
            }

        return {
            "success": True,
            "result": consensus.synthesis or consensus.winning_proposal.response,
            "consensus_type": consensus.consensus_type,
            "agreement_score": consensus.agreement_score,
            "dissenting_views": consensus.dissenting_views,
            "winning_agent": consensus.winning_proposal.agent_id,
        }

    except Exception as exc:
        logger.error("delegate_with_consensus failed: %s", exc, exc_info=True)
        return {
            "success": False,
            "result": None,
            "error": str(exc)[:300],
            "consensus_type": "error",
            "agreement_score": 0.0,
        }


def delegate_hierarchical(
    goal: str,
    agent_definitions: list[dict[str, Any]],
    context: dict[str, Any],
    *,
    tenant_id: str,
    run_id: str | None = None,
    on_event: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """Decompose a goal into sub-tasks, delegate each, and merge results.

    Args:
        goal: High-level natural-language goal.
        agent_definitions: List of dicts with ``id`` and ``description`` keys.
        context: Shared context for all sub-task agents.
        tenant_id: Active tenant.
        run_id: Optional parent run identifier.
        on_event: Optional callback for activity events.

    Returns:
        dict with keys: ``success``, ``result``, ``unmet_goals``, ``goal_tree_size``.
    """
    try:
        from api.services.agent.coordination.hierarchical_goals import GoalDecomposer

        effective_run_id = run_id or str(uuid.uuid4())
        decomposer = GoalDecomposer()
        tree = decomposer.decompose_goal(goal, agent_definitions)

        _emit(on_event, {
            "event_type": "hierarchical.decomposed",
            "goal": goal[:200],
            "sub_goal_count": len(tree.all_leaves()),
        })

        # Execute each leaf sub-goal via delegate_to_agent
        agent_results: dict[str, Any] = {}
        for node in tree.all_leaves():
            if not node.assigned_agent_id:
                logger.warning("Sub-goal has no assigned agent: %s", node.goal_text[:100])
                continue

            try:
                result = delegate_to_agent(
                    parent_agent_id="hierarchical_coordinator",
                    child_agent_id=node.assigned_agent_id,
                    task=node.goal_text,
                    context=context,
                    tenant_id=tenant_id,
                    run_id=effective_run_id,
                    on_event=on_event,
                )
                if result.get("success"):
                    agent_results[node.goal_text] = str(result.get("result") or "")
                else:
                    logger.warning(
                        "Sub-goal agent '%s' failed: %s",
                        node.assigned_agent_id,
                        result.get("error", "unknown"),
                    )
            except Exception as exc:
                logger.warning(
                    "Sub-goal execution failed for '%s': %s",
                    node.goal_text[:100], exc,
                )

        # Merge results
        merged = decomposer.merge_results(tree, agent_results)
        unmet = decomposer.validate_completeness(tree, agent_results)

        _emit(on_event, {
            "event_type": "hierarchical.complete",
            "goal": goal[:200],
            "completed_count": len(agent_results),
            "unmet_count": len(unmet),
        })

        return {
            "success": True,
            "result": merged,
            "unmet_goals": unmet,
            "goal_tree_size": len(tree.all_leaves()),
        }

    except Exception as exc:
        logger.error("delegate_hierarchical failed: %s", exc, exc_info=True)
        return {
            "success": False,
            "result": None,
            "error": str(exc)[:300],
            "unmet_goals": [],
            "goal_tree_size": 0,
        }
