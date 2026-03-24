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
        disable_auto_web_fallback=False,
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
        disable_auto_web_fallback=False,
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
        disable_auto_web_fallback=False,
    )


def test_should_auto_web_fallback_true_for_explicit_url_without_llm(monkeypatch) -> None:
    def _unexpected_llm_call(**_: Any) -> dict[str, Any]:
        raise AssertionError("LLM router should not run for explicit URL heuristic")

    monkeypatch.setattr(chat_app, "call_json_response", _unexpected_llm_call)

    assert chat_app._should_auto_web_fallback(
        message="https://axongroup.com what is this company doing?",
        chat_history=_empty_history(),
        disable_auto_web_fallback=False,
    )


def test_should_auto_web_fallback_true_for_recent_url_context_without_llm(monkeypatch) -> None:
    def _unexpected_llm_call(**_: Any) -> dict[str, Any]:
        raise AssertionError("LLM router should not run when recent URL context is present")

    monkeypatch.setattr(chat_app, "call_json_response", _unexpected_llm_call)

    assert chat_app._should_auto_web_fallback(
        message="what is their contact details",
        chat_history=[["https://axongroup.com what is this company doing?", "Summary answer"]],
        disable_auto_web_fallback=False,
    )


def test_should_auto_web_fallback_false_when_request_disables_it(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_app,
        "call_json_response",
        lambda **_: {"route": "web", "confidence": 0.99, "reason": "would route web"},
    )

    assert not chat_app._should_auto_web_fallback(
        message="latest public company revenue",
        chat_history=_empty_history(),
        disable_auto_web_fallback=True,
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


def test_run_chat_turn_rag_request_does_not_switch_to_web_command(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(chat_app, "API_CHAT_FAST_PATH", True)
    monkeypatch.setattr(chat_app, "run_fast_chat_turn", lambda **_: None)
    def fake_should_auto_web_fallback(**kwargs: Any) -> bool:
        captured["disable_auto_web_fallback"] = kwargs.get("disable_auto_web_fallback")
        return False

    monkeypatch.setattr(chat_app, "_should_auto_web_fallback", fake_should_auto_web_fallback)
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
        request=ChatRequest(
            message="Answer from my uploaded files only.",
            setting_overrides={"__rag_mode_enabled": True, "__disable_auto_web_fallback": True},
        ),
    )

    assert captured.get("disable_auto_web_fallback") is True
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


def test_apply_deep_search_defaults_expands_selected_sources(monkeypatch) -> None:
    class _DummyContext:
        app = SimpleNamespace(index_manager=SimpleNamespace(indices=[SimpleNamespace(id=7)]))

    monkeypatch.setattr(chat_app, "_classify_deep_search_complexity", lambda *_: "normal")
    monkeypatch.setattr(
        chat_app,
        "_list_index_source_ids",
        lambda **_: ["file-a", "file-b", "file-c"],
    )

    request = ChatRequest(
        message="Deep search on energy trends",
        agent_mode="deep_search",
    )
    updated = chat_app._apply_deep_search_defaults(
        context=_DummyContext(),  # type: ignore[arg-type]
        user_id="u1",
        request=request,
    )

    assert updated.setting_overrides.get("__deep_search_enabled") is True
    assert updated.setting_overrides.get("__deep_search_prompt_scoped_pdfs") is False
    assert updated.setting_overrides.get("__deep_search_user_selected_files") is False
    assert int(updated.setting_overrides.get("__research_web_search_budget") or 0) == 100
    assert "7" in updated.index_selection
    assert updated.index_selection["7"].mode == "select"
    assert updated.index_selection["7"].file_ids == ["file-a", "file-b", "file-c"]


def test_apply_deep_search_defaults_complex_profile_uses_higher_budget(monkeypatch) -> None:
    class _DummyContext:
        app = SimpleNamespace(index_manager=SimpleNamespace(indices=[SimpleNamespace(id=7)]))

    monkeypatch.setattr(chat_app, "_classify_deep_search_complexity", lambda *_: "complex")
    monkeypatch.setattr(chat_app, "_list_index_source_ids", lambda **_: ["file-a", "file-b"])

    request = ChatRequest(
        message="Deep research with broad evidence and comparative analysis.",
        agent_mode="deep_search",
    )
    updated = chat_app._apply_deep_search_defaults(
        context=_DummyContext(),  # type: ignore[arg-type]
        user_id="u1",
        request=request,
    )

    assert int(updated.setting_overrides.get("__research_web_search_budget") or 0) == 180
    assert int(updated.setting_overrides.get("__research_source_budget_min") or 0) == 120
    assert int(updated.setting_overrides.get("__research_source_budget_max") or 0) == 180
    assert int(updated.setting_overrides.get("__research_min_unique_sources") or 0) >= 50


def test_apply_deep_search_defaults_prefers_prompt_scoped_pdf_ids(monkeypatch) -> None:
    class _DummyContext:
        app = SimpleNamespace(
            index_manager=SimpleNamespace(indices=[SimpleNamespace(id=7), SimpleNamespace(id=8)])
        )

    monkeypatch.setattr(chat_app, "_classify_deep_search_complexity", lambda *_: "normal")
    monkeypatch.setattr(
        chat_app,
        "_resolve_prompt_scoped_pdf_ids",
        lambda **_: {8: ["pdf-1", "pdf-2"]},
    )
    monkeypatch.setattr(chat_app, "_list_index_source_ids", lambda **_: ["fallback-a", "fallback-b"])

    request = ChatRequest(
        message="Deep search the Alpha group PDFs.",
        agent_mode="deep_search",
        index_selection={"7": {"mode": "select", "file_ids": ["existing"]}},
    )
    updated = chat_app._apply_deep_search_defaults(
        context=_DummyContext(),  # type: ignore[arg-type]
        user_id="u1",
        request=request,
    )

    assert updated.index_selection["7"].file_ids[0] == "existing"
    assert updated.index_selection["8"].mode == "select"
    assert updated.index_selection["8"].file_ids == ["pdf-1", "pdf-2"]
    assert updated.setting_overrides.get("__deep_search_prompt_scoped_pdfs") is True
    assert updated.setting_overrides.get("__deep_search_user_selected_files") is True


def test_run_chat_turn_skips_fast_path_for_deep_search(monkeypatch) -> None:
    class _DummyIterator:
        def __iter__(self):
            return self

        def __next__(self):
            raise StopIteration(
                {
                    "conversation_id": "c1",
                    "conversation_name": "Conversation",
                    "message": "deep",
                    "answer": "ok",
                    "info": "",
                    "plot": None,
                    "state": {},
                    "mode": "deep_search",
                    "actions_taken": [],
                    "sources_used": [],
                    "source_usage": [],
                    "next_recommended_steps": [],
                    "needs_human_review": False,
                    "human_review_notes": None,
                    "web_summary": {},
                    "activity_run_id": None,
                    "info_panel": {},
                    "mindmap": {},
                }
            )

    called = {"fast_path": False}
    monkeypatch.setattr(chat_app, "API_CHAT_FAST_PATH", True)
    monkeypatch.setattr(
        chat_app,
        "run_fast_chat_turn",
        lambda **_: called.__setitem__("fast_path", True),
    )
    monkeypatch.setattr(chat_app, "_apply_deep_search_defaults", lambda **kwargs: kwargs["request"])
    monkeypatch.setattr(chat_app, "_auto_index_urls_for_request", lambda **kwargs: kwargs["request"])
    monkeypatch.setattr(chat_app, "stream_chat_turn", lambda **_: _DummyIterator())

    result = chat_app.run_chat_turn(
        context=object(),  # type: ignore[arg-type]
        user_id="u1",
        request=ChatRequest(message="run deep search", agent_mode="deep_search"),
    )

    assert called["fast_path"] is False
    assert result.get("mode") == "deep_search"


def test_resolve_chat_timeout_seconds_uses_deep_search_budget(monkeypatch) -> None:
    monkeypatch.setattr(chat_app.flowsettings, "KH_CHAT_TIMEOUT_SECONDS", 45, raising=False)
    monkeypatch.setattr(chat_app.flowsettings, "KH_CHAT_TIMEOUT_SECONDS_COMPANY_AGENT", 120, raising=False)
    monkeypatch.setattr(chat_app.flowsettings, "KH_CHAT_TIMEOUT_SECONDS_DEEP_SEARCH", 240, raising=False)
    monkeypatch.setattr(chat_app.flowsettings, "KH_CHAT_TIMEOUT_SECONDS_LOCAL_OLLAMA", 180, raising=False)
    monkeypatch.setattr(chat_app, "_default_model_looks_local_ollama", lambda: False)

    ask_timeout = chat_app._resolve_chat_timeout_seconds(requested_mode="ask")
    agent_timeout = chat_app._resolve_chat_timeout_seconds(requested_mode="company_agent")
    deep_timeout = chat_app._resolve_chat_timeout_seconds(requested_mode="deep_search")

    assert ask_timeout == 45
    assert agent_timeout == 120
    assert deep_timeout == 240


def test_resolve_chat_timeout_seconds_respects_local_ollama_floor(monkeypatch) -> None:
    monkeypatch.setattr(chat_app.flowsettings, "KH_CHAT_TIMEOUT_SECONDS", 45, raising=False)
    monkeypatch.setattr(chat_app.flowsettings, "KH_CHAT_TIMEOUT_SECONDS_DEEP_SEARCH", 240, raising=False)
    monkeypatch.setattr(chat_app.flowsettings, "KH_CHAT_TIMEOUT_SECONDS_LOCAL_OLLAMA", 300, raising=False)
    monkeypatch.setattr(chat_app, "_default_model_looks_local_ollama", lambda: True)

    deep_timeout = chat_app._resolve_chat_timeout_seconds(requested_mode="deep_search")
    assert deep_timeout == 300
