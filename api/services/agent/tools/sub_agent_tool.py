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
            "sequential sub-tasks (e.g. research → write → send)."
        ),
    )

    def execute(
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
            raise ToolExecutionError("`child_agent_id` is required.")
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
