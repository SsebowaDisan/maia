from __future__ import annotations

from typing import Any

from api.schemas import ChatRequest
from api.services.chat import app_stream_orchestrator as orchestrator_stream


class _DummyAgentResult:
    def __init__(self, *, answer: str, info_html: str) -> None:
        self.run_id = "run-test"
        self.answer = answer
        self.info_html = info_html
        self.actions_taken: list[Any] = []
        self.sources_used: list[Any] = []
        self.evidence_items: list[dict[str, Any]] = []
        self.next_recommended_steps: list[str] = []
        self.needs_human_review = False
        self.human_review_notes = ""
        self.web_summary: dict[str, Any] = {}


class _DummyOrchestrator:
    def __init__(self, result: _DummyAgentResult) -> None:
        self._result = result

    def run_stream(self, **_: Any):
        if False:
            yield {}
        return self._result


def _collect_stream_events(stream):
    events: list[dict[str, Any]] = []
    result: dict[str, Any] | None = None
    while True:
        try:
            events.append(next(stream))
        except StopIteration as stop:
            result = stop.value
            break
    return events, result or {}


def test_orchestrator_stream_emits_citation_enriched_chat_delta(monkeypatch) -> None:
    agent_result = _DummyAgentResult(
        answer="Uganda has strong agricultural potential.",
        info_html=(
            "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='2' open>"
            "<summary><i>Evidence [1]</i></summary>"
            "<div class='evidence-content'><b>Extract:</b> Agriculture drives national output.</div>"
            "</details>"
        ),
    )

    monkeypatch.setattr(
        orchestrator_stream,
        "get_orchestrator",
        lambda: _DummyOrchestrator(agent_result),
    )
    monkeypatch.setattr(orchestrator_stream, "persist_conversation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(orchestrator_stream, "build_info_panel_copy", lambda **_kwargs: {})

    request = ChatRequest(
        message="Research Uganda economy",
        agent_mode="company_agent",
        citation="inline",
    )
    stream = orchestrator_stream.run_orchestrator_stream_turn(
        request=request,
        user_id="u1",
        message=request.message,
        settings={},
        conversation_id="c1",
        conversation_name="Conversation",
        data_source={},
        chat_history=[],
        chat_state={},
        persisted_workspace_ids={
            "deep_research_doc_id": "",
            "deep_research_doc_url": "",
            "deep_research_sheet_id": "",
            "deep_research_sheet_url": "",
        },
        selected_payload={},
        turn_attachments=[],
        requested_mode="company_agent",
        mode_variant="",
        capture_workspace_ids_from_actions_fn=lambda _actions: {
            "deep_research_doc_id": "",
            "deep_research_doc_url": "",
            "deep_research_sheet_id": "",
            "deep_research_sheet_url": "",
        },
        extract_plot_from_actions_fn=lambda _actions: None,
    )

    events, final_payload = _collect_stream_events(stream)
    chat_events = [event for event in events if event.get("type") == "chat_delta"]

    assert chat_events, "Expected at least one streamed chat delta event."
    assert "class='citation'" in str(chat_events[-1].get("text") or "")
    assert "class='citation'" in str(final_payload.get("answer") or "")
