from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.orchestration.app import AgentOrchestrator


def test_build_execution_prompt_includes_session_and_memory_context() -> None:
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    request = ChatRequest(message="Build the report", agent_mode="company_agent")
    prompt = AgentOrchestrator._build_execution_prompt(
        orchestrator,
        request=request,
        settings={
            "__conversation_summary": "User asked for a concise report.",
            "__working_context_preview": "Objective: Build report | Unresolved slots: 1",
            "__conversation_snippets": ["Use evidence from verified sources."],
            "__session_context_snippets": ["Previous run: report format with executive summary."],
            "__memory_context_snippets": ["Playbook: include verification and next steps."],
        },
    )
    assert "Working context:" in prompt
    assert "Conversation context:" in prompt
    assert "Recent snippets:" in prompt
    assert "Recent session memory:" in prompt
    assert "Relevant past memory:" in prompt


def test_build_scoped_execution_prompt_includes_role_and_obligations() -> None:
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    prompt = AgentOrchestrator._build_scoped_execution_prompt(
        orchestrator,
        base_prompt="Build the report",
        owner_role="writer",
        scoped_working_context={
            "preview": "Objective: Build report",
            "verification_obligations": ["content matches verified evidence"],
        },
    )
    assert "Active role: writer" in prompt
    assert "Role-scoped context:" in prompt
    assert "Role verification obligations:" in prompt
