from __future__ import annotations

import json
from urllib.error import HTTPError

from api.services.agent import llm_runtime


class _FakeResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_call_openai_chat_retries_on_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MAIA_AGENT_LLM_RETRIES", "2")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(llm_runtime.time, "sleep", lambda _: None)

    calls = {"count": 0}

    def _fake_urlopen(request_obj, timeout=0):
        del request_obj, timeout
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError(url="", code=429, msg="rate limit", hdrs=None, fp=None)
        return _FakeResponse({"choices": [{"message": {"content": [{"type": "text", "text": '{"ok": true}'}]}}]})

    monkeypatch.setattr(llm_runtime, "urlopen", _fake_urlopen)
    payload = llm_runtime.call_openai_chat(messages=[{"role": "user", "content": "hello"}], temperature=0.0)

    assert isinstance(payload, dict)
    assert calls["count"] == 2


def test_call_openai_chat_uses_fallback_model(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MAIA_AGENT_LLM_RETRIES", "1")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-primary")
    monkeypatch.setenv("OPENAI_CHAT_MODEL_FALLBACKS", "gpt-secondary")

    seen_models: list[str] = []

    def _fake_urlopen(request_obj, timeout=0):
        del timeout
        body = json.loads(request_obj.data.decode("utf-8"))
        model = str(body.get("model") or "")
        seen_models.append(model)
        if model == "gpt-primary":
            raise HTTPError(url="", code=400, msg="bad request", hdrs=None, fp=None)
        return _FakeResponse({"choices": [{"message": {"content": [{"type": "text", "text": '{"ok": true}'}]}}]})

    monkeypatch.setattr(llm_runtime, "urlopen", _fake_urlopen)
    payload = llm_runtime.call_openai_chat(messages=[{"role": "user", "content": "hello"}], temperature=0.0)

    assert isinstance(payload, dict)
    assert seen_models == ["gpt-primary", "gpt-secondary"]


def test_call_json_response_repair_pass(monkeypatch) -> None:
    responses = iter(
        [
            {"choices": [{"message": {"content": [{"type": "text", "text": "not json"}]}}]},
            {"choices": [{"message": {"content": [{"type": "text", "text": '{"objective":"ok"}'}]}}]},
        ]
    )

    monkeypatch.setattr(llm_runtime, "call_openai_chat", lambda **kwargs: next(responses))
    payload = llm_runtime.call_json_response(
        system_prompt="system",
        user_prompt="user",
        temperature=0.0,
    )

    assert payload == {"objective": "ok"}
