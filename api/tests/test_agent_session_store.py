from __future__ import annotations

from pathlib import Path

from api.services.agent.orchestration.session_store import SessionStore


def test_session_store_upserts_and_lists_by_update_time(tmp_path: Path) -> None:
    store = SessionStore(root=tmp_path / ".maia_agent_test")
    first = store.save_session_run(
        {
            "run_id": "run_1",
            "user_id": "u1",
            "conversation_id": "c1",
            "message": "Analyze website",
            "answer": "Initial answer",
        }
    )
    updated = store.save_session_run(
        {
            "run_id": "run_1",
            "user_id": "u1",
            "conversation_id": "c1",
            "message": "Analyze website deeply",
            "answer": "Updated answer",
        }
    )
    assert first["run_id"] == "run_1"
    assert updated["run_id"] == "run_1"
    assert updated["answer"] == "Updated answer"
    rows = store.list_session_runs(user_id="u1", conversation_id="c1", limit=5)
    assert len(rows) == 1
    assert rows[0]["message"] == "Analyze website deeply"


def test_session_store_retrieves_semantic_context_snippets(tmp_path: Path) -> None:
    store = SessionStore(root=tmp_path / ".maia_agent_test")
    store.save_session_run(
        {
            "run_id": "run_alpha",
            "user_id": "u1",
            "conversation_id": "c1",
            "message": "Research machine learning trends",
            "agent_goal": "Find machine learning updates",
            "answer": "ML adoption is increasing.",
        }
    )
    store.save_session_run(
        {
            "run_id": "run_beta",
            "user_id": "u1",
            "conversation_id": "c2",
            "message": "Analyze supply chain costs",
            "agent_goal": "Cost optimization",
            "answer": "Transport costs increased by 7%.",
        }
    )
    snippets = store.retrieve_context_snippets(
        query="latest machine learning adoption",
        user_id="u1",
        conversation_id="c1",
        limit=3,
    )
    assert snippets
    assert any("machine learning" in row.lower() for row in snippets)

