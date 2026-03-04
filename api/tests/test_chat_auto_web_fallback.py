from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from api.schemas import ChatRequest
from api.services.chat import app as chat_app


def _empty_history() -> list[list[str]]:
    return []


def test_should_auto_web_fallback_true_on_web_route(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_app,
        "call_json_response",
        lambda **_: {"route": "web", "confidence": 0.93, "reason": "needs live data"},
    )

    assert chat_app._should_auto_web_fallback(
        message="What is the latest revenue for this public company?",
        chat_history=_empty_history(),
    )


def test_should_auto_web_fallback_false_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_CHAT_AUTO_WEB_FALLBACK_ENABLED", "0")
    monkeypatch.setattr(
        chat_app,
        "call_json_response",
        lambda **_: {"route": "web", "confidence": 0.99, "reason": "would route web"},
    )

    assert not chat_app._should_auto_web_fallback(
        message="Any question",
        chat_history=_empty_history(),
    )


def test_should_auto_web_fallback_false_for_local_route(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_app,
        "call_json_response",
        lambda **_: {"route": "local", "confidence": 0.88, "reason": "indexed context enough"},
    )

    assert not chat_app._should_auto_web_fallback(
        message="Summarize this document",
        chat_history=_empty_history(),
    )


def test_should_auto_web_fallback_true_for_explicit_url_without_llm(monkeypatch) -> None:
    def _unexpected_llm_call(**_: Any) -> dict[str, Any]:
        raise AssertionError("LLM router should not run for explicit URL heuristic")

    monkeypatch.setattr(chat_app, "call_json_response", _unexpected_llm_call)

    assert chat_app._should_auto_web_fallback(
        message="https://axongroup.com what is this company doing?",
        chat_history=_empty_history(),
    )


def test_should_auto_web_fallback_true_for_recent_url_context_without_llm(monkeypatch) -> None:
    def _unexpected_llm_call(**_: Any) -> dict[str, Any]:
        raise AssertionError("LLM router should not run when recent URL context is present")

    monkeypatch.setattr(chat_app, "call_json_response", _unexpected_llm_call)

    assert chat_app._should_auto_web_fallback(
        message="what is their contact details",
        chat_history=[["https://axongroup.com what is this company doing?", "Summary answer"]],
    )


def test_run_chat_turn_switches_to_web_command_when_router_says_web(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(chat_app, "API_CHAT_FAST_PATH", True)
    monkeypatch.setattr(chat_app, "run_fast_chat_turn", lambda **_: None)
    monkeypatch.setattr(chat_app, "_should_auto_web_fallback", lambda **_: True)
    monkeypatch.setattr(
        chat_app,
        "get_or_create_conversation",
        lambda **_: ("c1", "Conversation", {"messages": []}),
    )

    def fake_stream_chat_turn(context, user_id, request):
        del context, user_id
        captured["command"] = request.command
        if False:
            yield {}
        return {"ok": True, "command": request.command}

    monkeypatch.setattr(chat_app, "stream_chat_turn", fake_stream_chat_turn)

    result = chat_app.run_chat_turn(
        context=object(),  # type: ignore[arg-type]
        user_id="u1",
        request=ChatRequest(message="Find latest market updates"),
    )

    assert captured.get("command") == chat_app.WEB_SEARCH_COMMAND
    assert result.get("command") == chat_app.WEB_SEARCH_COMMAND


def test_run_chat_turn_keeps_command_when_router_says_local(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(chat_app, "API_CHAT_FAST_PATH", True)
    monkeypatch.setattr(chat_app, "run_fast_chat_turn", lambda **_: None)
    monkeypatch.setattr(chat_app, "_should_auto_web_fallback", lambda **_: False)
    monkeypatch.setattr(
        chat_app,
        "get_or_create_conversation",
        lambda **_: ("c1", "Conversation", {"messages": []}),
    )

    def fake_stream_chat_turn(context, user_id, request):
        del context, user_id
        captured["command"] = request.command
        if False:
            yield {}
        return {"ok": True, "command": request.command}

    monkeypatch.setattr(chat_app, "stream_chat_turn", fake_stream_chat_turn)

    result = chat_app.run_chat_turn(
        context=object(),  # type: ignore[arg-type]
        user_id="u1",
        request=ChatRequest(message="Summarize local docs"),
    )

    assert captured.get("command") in (None, "")
    assert result.get("command") in (None, "")


def test_auto_index_urls_for_request_merges_index_selection(monkeypatch) -> None:
    class _DummyContext:
        app = SimpleNamespace(index_manager=SimpleNamespace(indices=[SimpleNamespace(id=7)]))

    monkeypatch.setattr(chat_app, "load_user_settings", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        chat_app,
        "index_urls",
        lambda **_: {
            "index_id": 7,
            "file_ids": ["url-file-1", "url-file-2"],
            "errors": [],
            "items": [],
            "debug": [],
        },
    )

    request = ChatRequest(message="https://axongroup.com/ what is this company doing?")
    updated = chat_app._auto_index_urls_for_request(
        context=_DummyContext(),  # type: ignore[arg-type]
        user_id="u1",
        request=request,
        settings={},
    )

    assert "7" in updated.index_selection
    assert updated.index_selection["7"].mode == "select"
    assert updated.index_selection["7"].file_ids == ["url-file-1", "url-file-2"]
    assert bool(updated.setting_overrides.get("__auto_url_indexed")) is True


def test_auto_index_urls_for_request_keeps_existing_select_ids(monkeypatch) -> None:
    class _DummyContext:
        app = SimpleNamespace(index_manager=SimpleNamespace(indices=[SimpleNamespace(id=3)]))

    monkeypatch.setattr(chat_app, "load_user_settings", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        chat_app,
        "index_urls",
        lambda **_: {
            "index_id": 3,
            "file_ids": ["new-url-file"],
            "errors": [],
            "items": [],
            "debug": [],
        },
    )

    monkeypatch.setenv("MAIA_CHAT_STRICT_URL_GROUNDING", "0")

    request = ChatRequest(
        message="Read this https://example.com/about",
        index_selection={"3": {"mode": "select", "file_ids": ["existing-file"]}},
    )
    updated = chat_app._auto_index_urls_for_request(
        context=_DummyContext(),  # type: ignore[arg-type]
        user_id="u1",
        request=request,
        settings={},
    )

    assert updated.index_selection["3"].mode == "select"
    assert updated.index_selection["3"].file_ids == ["existing-file", "new-url-file"]


def test_auto_index_urls_for_request_strict_grounding_overrides_existing_select_ids(monkeypatch) -> None:
    class _DummyContext:
        app = SimpleNamespace(index_manager=SimpleNamespace(indices=[SimpleNamespace(id=3)]))

    monkeypatch.setattr(chat_app, "load_user_settings", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        chat_app,
        "index_urls",
        lambda **_: {
            "index_id": 3,
            "file_ids": ["new-url-file"],
            "errors": [],
            "items": [],
            "debug": [],
        },
    )

    request = ChatRequest(
        message="Read this https://example.com/about",
        index_selection={"3": {"mode": "select", "file_ids": ["existing-file"]}},
    )
    updated = chat_app._auto_index_urls_for_request(
        context=_DummyContext(),  # type: ignore[arg-type]
        user_id="u1",
        request=request,
        settings={},
    )

    assert updated.index_selection["3"].mode == "select"
    assert updated.index_selection["3"].file_ids == ["new-url-file"]


def test_auto_index_urls_for_request_skips_when_marker_present(monkeypatch) -> None:
    class _DummyContext:
        app = SimpleNamespace(index_manager=SimpleNamespace(indices=[SimpleNamespace(id=1)]))

    called = {"index_urls": False}

    def _unexpected_index(**_: Any) -> dict[str, Any]:
        called["index_urls"] = True
        return {"index_id": 1, "file_ids": ["x"], "errors": [], "items": [], "debug": []}

    monkeypatch.setattr(chat_app, "index_urls", _unexpected_index)

    request = ChatRequest(
        message="https://example.com",
        setting_overrides={"__auto_url_indexed": True},
    )
    updated = chat_app._auto_index_urls_for_request(
        context=_DummyContext(),  # type: ignore[arg-type]
        user_id="u1",
        request=request,
        settings={},
    )

    assert called["index_urls"] is False
    assert updated.setting_overrides.get("__auto_url_indexed") is True
