from __future__ import annotations

from api.services.agent.orchestration.working_context import (
    compile_working_context,
    scoped_working_context_for_role,
)


def test_compile_working_context_contains_required_sections() -> None:
    context = compile_working_context(
        seed={
            "message": "Analyze website and send report",
            "agent_goal": "Research site and draft report",
            "rewritten_task": "Analyze the website, collect evidence, write report",
            "intent_tags": ["web_research", "reporting"],
            "task_contract": {
                "objective": "Analyze website and send report",
                "required_outputs": ["Report summary"],
                "required_facts": ["Company domains"],
                "required_actions": ["send_email"],
                "delivery_target": "team@example.com",
                "success_checks": ["Citations included"],
            },
            "contract_missing_slots": [
                {
                    "requirement": "Recipient name",
                    "description": "Name of recipient",
                    "discoverable": False,
                    "blocking": True,
                    "state": "open",
                    "resolved_value": "",
                }
            ],
            "conversation_summary": "User wants a concise, factual answer.",
            "conversation_snippets": ["Use citations."],
            "selected_file_ids": ["file_a", "file_b"],
            "selected_index_id": 7,
            "planned_search_terms": ["company profile"],
            "planned_keywords": ["safety", "quality"],
            "session_context_snippets": ["Last run used the same source structure."],
            "memory_context_snippets": ["Playbook requires verification first."],
        }
    )

    assert context["version"] == "working_context_v1"
    sections = context.get("sections", {})
    assert isinstance(sections, dict)
    assert "request" in sections
    assert "contract" in sections
    assert "slots" in sections
    assert "history" in sections
    assert "artifacts" in sections
    assert "memory" in sections
    assert "Objective:" in str(context.get("preview") or "")


def test_scoped_working_context_for_role_contains_role_metadata() -> None:
    context = compile_working_context(
        seed={
            "message": "Analyze website and send report",
            "task_contract": {"objective": "Analyze website"},
            "contract_missing_slots": [],
        }
    )
    scoped = scoped_working_context_for_role(
        working_context=context,
        role="writer",
    )
    assert scoped["role"] == "writer"
    assert scoped["role_summary"]
    assert isinstance(scoped.get("verification_obligations"), list)
    artifacts = scoped.get("sections", {}).get("artifacts", {})
    assert artifacts.get("role") == "writer"
