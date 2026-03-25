from __future__ import annotations

import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError

from api.services.chat import fast_qa_runtime_helpers as helpers


def test_resolve_fast_qa_llm_config_prefers_neutral_maia_aliases() -> None:
    values = {
        "MAIA_LLM_API_BASE": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "MAIA_LLM_API_KEY": "sk-qwen-test",
        "MAIA_LLM_CHAT_MODEL": "qwen-plus-latest",
        "OPENAI_API_BASE": "https://api.openai.com/v1",
        "OPENAI_API_KEY": "sk-openai-test",
        "OPENAI_CHAT_MODEL": "gpt-4o-mini",
    }

    def _config(name: str, default: str = "") -> str:
        return values.get(name, default)

    llms_manager = SimpleNamespace(get_default_name=lambda: "", info=lambda: {})
    api_key, base_url, model, source = helpers.resolve_fast_qa_llm_config(
        config_fn=_config,
        is_placeholder_api_key_fn=lambda value: not str(value).strip(),
        llms_manager=llms_manager,
    )

    assert api_key == "sk-qwen-test"
    assert base_url == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    assert model == "qwen-plus-latest"
    assert source == "env"


def test_infer_openai_compatible_provider_detects_qwen_dashscope() -> None:
    provider = helpers.infer_openai_compatible_provider(
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus-latest",
    )

    assert provider == "qwen-dashscope"


def test_call_openai_chat_text_retries_transient_http_429(monkeypatch) -> None:
    calls = {"count": 0}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {"message": {"content": "ok"}}
                    ]
                }
            ).encode("utf-8")

    def _fake_urlopen(_request, timeout=0):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError(
                url="https://example.com/v1/chat/completions",
                code=429,
                msg="Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(b'{"error":{"message":"rate limited"}}'),
            )
        return _Resp()

    monkeypatch.setattr(helpers, "urlopen", _fake_urlopen)
    monkeypatch.setattr(helpers.time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("MAIA_FAST_QA_LLM_RETRIES", "2")

    result = helpers.call_openai_chat_text(
        api_key="test-key",
        base_url="https://example.com/v1",
        request_payload={"model": "demo", "messages": [{"role": "user", "content": "hi"}]},
        timeout_seconds=10,
        extract_text_content_fn=lambda raw: str(raw or "").strip(),
    )

    assert result == "ok"
    assert calls["count"] == 2


def test_prepare_openai_compatible_payload_adds_gemini_thinking_config() -> None:
    payload = helpers._prepare_openai_compatible_payload(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        request_payload={"model": "gemini-2.5-flash", "messages": [{"role": "user", "content": "hi"}]},
    )

    extra = payload.get("extra_body")
    assert isinstance(extra, dict)
    google = extra.get("google")
    assert isinstance(google, dict)
    thinking = google.get("thinking_config")
    assert isinstance(thinking, dict)
    assert thinking.get("thinking_budget") == 0
