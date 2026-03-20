"""Sub-agent delegation tool.

Inspired by deepagents' ``task`` tool — spawns a child agent with an isolated
context window so the orchestrator can break long multi-step workflows into
focused sub-tasks without exploding the main context window.

Usage by the agent:
  tool_id:  agent.delegate
  params:
    child_agent_id: str   — ID of an installed marketplace/custom agent
    task:           str   — Natural-language task for the child agent
    context:        dict  — Optional key/value facts to inject into child context
"""
from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)


class SubAgentDelegateTool(AgentTool):
    """Delegate a focused sub-task to another installed agent.

    The child agent runs with its own context window and system prompt, returning
    its full text output as the tool result.  This prevents context explosion for
    long research-or-execution workflows composed of independent sub-tasks.
    """

    metadata = ToolMetadata(
        tool_id="agent.delegate",
        action_class="execute",
        risk_level="medium",
        required_permissions=[],
        execution_policy="auto_execute",
        description=(
            "Delegate a focused sub-task to another installed agent with an isolated "
            "context window. Use this to break multi-step workflows into scoped "
            "sequential sub-tasks (e.g. research → write → send). "
            "Supports modes: 'delegate' (default single-agent), 'consensus' "
            "(multi-agent consensus), 'hierarchical' (goal decomposition)."
        ),
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        mode = str(params.get("mode") or "delegate").strip().lower()

        if mode == "consensus":
            return self._execute_consensus(context=context, prompt=prompt, params=params)
        elif mode == "hierarchical":
            return self._execute_hierarchical(context=context, prompt=prompt, params=params)
        else:
            return self._execute_delegate(context=context, prompt=prompt, params=params)

    @staticmethod
    def _resolve_child_agent_id(*, context: ToolExecutionContext, task: str) -> str:
        try:
            from api.services.agents.definition_store import list_agents
        except Exception:
            return ""

        try:
            rows = list_agents(context.tenant_id)
        except Exception:
            return ""

        task_text = str(task or "").strip().lower()
        if not isinstance(rows, list) or not rows:
            return ""

        def _score(label: str) -> int:
            lowered = str(label or "").strip().lower()
            if not lowered:
                return 0
            score = 0
            hints: dict[str, tuple[str, ...]] = {
                "researcher": ("research", "source", "fact", "finding", "search", "web"),
                "analyst": ("analysis", "analy", "insight", "compare", "statistic"),
                "writer": ("write", "draft", "report", "summary"),
                "deliverer": ("deliver", "send", "email", "publish"),
                "browser": ("browser", "navigate", "extract", "website"),
            }
            for role, keywords in hints.items():
                if role in lowered:
                    score += 4
                if any(keyword in task_text for keyword in keywords) and role in lowered:
                    score += 6
            if lowered and lowered in task_text:
                score += 2
            return score

        best_id = ""
        best_score = -1
        for row in rows:
            candidate_id = str(getattr(row, "agent_id", None) or getattr(row, "id", None) or "").strip()
            candidate_name = str(getattr(row, "name", None) or "").strip()
            if not candidate_id:
                continue
            candidate_score = max(_score(candidate_id), _score(candidate_name))
            if candidate_score > best_score:
                best_score = candidate_score
                best_id = candidate_id

        if best_id:
            return best_id
        first = rows[0]
        return str(getattr(first, "agent_id", None) or getattr(first, "id", None) or "").strip()

    # ── mode="delegate" (original behaviour) ──────────────────────────────

    def _execute_delegate(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        from api.services.agents.orchestrator import DelegationDepthError, delegate_to_agent

        child_agent_id = str(params.get("child_agent_id") or "").strip()
        task = str(params.get("task") or prompt or "").strip()
        extra_context: dict[str, Any] = dict(params.get("context") or {})

        if not child_agent_id:
            child_agent_id = self._resolve_child_agent_id(context=context, task=task)
        if not child_agent_id:
            raise ToolExecutionError("`child_agent_id` is required and could not be auto-resolved.")
        if not task:
            raise ToolExecutionError("`task` is required.")

        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="agent.delegate_start",
                title=f"Delegating to {child_agent_id}",
                detail=task[:200],
                data={
                    "child_agent_id": child_agent_id,
                    "task_preview": task[:200],
                    "scene_surface": "system",
                },
            )
        ]

        try:
            result = delegate_to_agent(
                parent_agent_id="company_agent",
                child_agent_id=child_agent_id,
                task=task,
                context=extra_context,
                tenant_id=context.tenant_id,
                run_id=context.run_id,
            )
        except DelegationDepthError as exc:
            raise ToolExecutionError(str(exc)) from exc

        success = bool(result.get("success"))
        child_result = str(result.get("result") or "")
        child_run_id = str(result.get("child_run_id") or "")

        events.append(
            ToolTraceEvent(
                event_type="agent.delegate_done",
                title=f"Sub-task {'completed' if success else 'failed'}: {child_agent_id}",
                detail=child_result[:300] if success else str(result.get("error") or ""),
                data={
                    "child_agent_id": child_agent_id,
                    "child_run_id": child_run_id,
                    "success": success,
                    "scene_surface": "system",
                },
            )
        )

        if not success:
            raise ToolExecutionError(
                f"Sub-agent '{child_agent_id}' failed: "
                f"{result.get('error', 'unknown error')}"
            )

        return ToolExecutionResult(
            summary=f"Sub-task completed via {child_agent_id} ({len(child_result)} chars)",
            content=child_result,
            data={
                "child_agent_id": child_agent_id,
                "child_run_id": child_run_id,
                "result_length": len(child_result),
            },
            sources=[],
            next_steps=["Review sub-task output and proceed with the next workflow step."],
            events=events,
        )

    # ── mode="consensus" (Innovation #9) ──────────────────────────────────

    def _execute_consensus(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        try:
            from api.services.agents.orchestrator import delegate_with_consensus
        except ImportError as exc:
            raise ToolExecutionError(
                f"Consensus coordination not available: {exc}"
            ) from exc

        task = str(params.get("task") or prompt or "").strip()
        agent_ids: list[str] = list(params.get("agent_ids") or [])
        extra_context: dict[str, Any] = dict(params.get("context") or {})

        if not agent_ids or len(agent_ids) < 2:
            raise ToolExecutionError(
                "`agent_ids` must contain at least 2 agent IDs for consensus mode."
            )
        if not task:
            raise ToolExecutionError("`task` is required.")

        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="agent.consensus_start",
                title=f"Consensus across {len(agent_ids)} agents",
                detail=task[:200],
                data={
                    "agent_ids": agent_ids,
                    "task_preview": task[:200],
                    "scene_surface": "system",
                },
            )
        ]

        try:
            result = delegate_with_consensus(
                task=task,
                agent_ids=agent_ids,
                context=extra_context,
                tenant_id=context.tenant_id,
                run_id=context.run_id,
            )
        except Exception as exc:
            raise ToolExecutionError(f"Consensus delegation failed: {exc}") from exc

        success = bool(result.get("success"))
        consensus_result = str(result.get("result") or "")
        consensus_type = str(result.get("consensus_type", "unknown"))

        events.append(
            ToolTraceEvent(
                event_type="agent.consensus_done",
                title=f"Consensus: {consensus_type}",
                detail=consensus_result[:300] if success else str(result.get("error") or ""),
                data={
                    "consensus_type": consensus_type,
                    "agreement_score": result.get("agreement_score", 0.0),
                    "winning_agent": result.get("winning_agent", ""),
                    "success": success,
                    "scene_surface": "system",
                },
            )
        )

        if not success:
            raise ToolExecutionError(
                f"Consensus failed: {result.get('error', 'unknown error')}"
            )

        return ToolExecutionResult(
            summary=(
                f"Consensus ({consensus_type}) from {len(agent_ids)} agents "
                f"({len(consensus_result)} chars)"
            ),
            content=consensus_result,
            data={
                "consensus_type": consensus_type,
                "agreement_score": result.get("agreement_score", 0.0),
                "winning_agent": result.get("winning_agent", ""),
                "dissenting_views": result.get("dissenting_views", []),
                "result_length": len(consensus_result),
            },
            sources=[],
            next_steps=["Review consensus result and proceed."],
            events=events,
        )

    # ── mode="hierarchical" ───────────────────────────────────────────────

    def _execute_hierarchical(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        try:
            from api.services.agents.orchestrator import delegate_hierarchical
        except ImportError as exc:
            raise ToolExecutionError(
                f"Hierarchical coordination not available: {exc}"
            ) from exc

        goal = str(params.get("goal") or params.get("task") or prompt or "").strip()
        agent_definitions: list[dict[str, Any]] = list(params.get("agent_definitions") or [])
        extra_context: dict[str, Any] = dict(params.get("context") or {})

        if not goal:
            raise ToolExecutionError("`goal` (or `task`) is required.")
        if not agent_definitions:
            raise ToolExecutionError(
                "`agent_definitions` (list of {id, description}) is required "
                "for hierarchical mode."
            )

        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="agent.hierarchical_start",
                title=f"Hierarchical goal: {goal[:80]}",
                detail=goal[:200],
                data={
                    "agent_count": len(agent_definitions),
                    "goal_preview": goal[:200],
                    "scene_surface": "system",
                },
            )
        ]

        try:
            result = delegate_hierarchical(
                goal=goal,
                agent_definitions=agent_definitions,
                context=extra_context,
                tenant_id=context.tenant_id,
                run_id=context.run_id,
            )
        except Exception as exc:
            raise ToolExecutionError(f"Hierarchical delegation failed: {exc}") from exc

        success = bool(result.get("success"))
        merged_result = str(result.get("result") or "")
        unmet_goals: list[str] = list(result.get("unmet_goals") or [])

        events.append(
            ToolTraceEvent(
                event_type="agent.hierarchical_done",
                title=f"Hierarchical {'completed' if success else 'failed'}",
                detail=merged_result[:300] if success else str(result.get("error") or ""),
                data={
                    "goal_tree_size": result.get("goal_tree_size", 0),
                    "unmet_count": len(unmet_goals),
                    "success": success,
                    "scene_surface": "system",
                },
            )
        )

        if not success:
            raise ToolExecutionError(
                f"Hierarchical delegation failed: {result.get('error', 'unknown error')}"
            )

        return ToolExecutionResult(
            summary=(
                f"Hierarchical goal completed ({result.get('goal_tree_size', 0)} sub-goals, "
                f"{len(unmet_goals)} unmet, {len(merged_result)} chars)"
            ),
            content=merged_result,
            data={
                "goal_tree_size": result.get("goal_tree_size", 0),
                "unmet_goals": unmet_goals,
                "result_length": len(merged_result),
            },
            sources=[],
            next_steps=[
                "Review hierarchical result.",
                *(
                    [f"Address unmet sub-goals: {', '.join(unmet_goals[:3])}"]
                    if unmet_goals else []
                ),
            ],
            events=events,
        )
