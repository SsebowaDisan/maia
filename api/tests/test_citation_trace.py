from api.services.observability.citation_trace import (
    begin_trace,
    end_trace,
    get_trace_id,
    record_trace_event,
    snapshot_trace,
)
import threading


def test_citation_trace_collects_request_scoped_events() -> None:
    handle = begin_trace(
        kind="chat",
        user_id="u1",
        question="What happened?",
        conversation_id="c1",
    )
    try:
        assert get_trace_id() == handle.trace_id
        record_trace_event("retrieval.started", {"query": "What happened?"})
        trace = snapshot_trace()
        assert trace["trace_id"] == handle.trace_id
        assert trace["kind"] == "chat"
        assert trace["user_id"] == "u1"
        assert trace["conversation_id"] == "c1"
        assert trace["event_count"] >= 2
        assert any(event["type"] == "retrieval.started" for event in trace["events"])
    finally:
        end_trace(handle, emit_log=False)

    assert get_trace_id() == ""


def test_end_trace_does_not_crash_on_context_mismatch() -> None:
    handle = begin_trace(kind="chat", user_id="u1", question="Cross-context cleanup")

    errors: list[Exception] = []

    def _worker() -> None:
        try:
            end_trace(handle, emit_log=False)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join(timeout=2)

    assert not errors

    # Ensure local test context is clean for subsequent tests.
    if get_trace_id():
        end_trace(handle, emit_log=False)
    assert get_trace_id() == ""
