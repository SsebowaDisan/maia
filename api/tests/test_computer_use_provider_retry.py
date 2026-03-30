from __future__ import annotations

from types import SimpleNamespace

from api.services.computer_use.providers import anthropic_provider, openai_provider


class _FakeException(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_openai_retry_classifier_handles_status_and_message() -> None:
    assert openai_provider._is_retryable_exception(_FakeException("rate limited", 429)) is True
    assert openai_provider._is_retryable_exception(_FakeException("server exploded", 500)) is True
    assert openai_provider._is_retryable_exception(_FakeException("bad request", 400)) is False
    assert openai_provider._is_retryable_exception(_FakeException("network timeout")) is True
    assert openai_provider._is_retryable_exception(_FakeException("invalid prompt")) is False


def test_anthropic_retry_classifier_handles_status_and_message() -> None:
    assert anthropic_provider._is_retryable_exception(_FakeException("rate limited", 429)) is True
    assert anthropic_provider._is_retryable_exception(_FakeException("internal error", 503)) is True
    assert anthropic_provider._is_retryable_exception(_FakeException("bad request", 400)) is False
    assert anthropic_provider._is_retryable_exception(_FakeException("connection reset by peer")) is True
    assert anthropic_provider._is_retryable_exception(_FakeException("unsupported tool")) is False


def test_openai_string_content_fallback_normalizes_structured_user_messages() -> None:
    messages = [
        {"role": "system", "content": "system"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Inspect the page"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        },
    ]

    normalized = openai_provider._coerce_user_content_to_string(messages)

    assert normalized[0]["content"] == "system"
    assert isinstance(normalized[1]["content"], str)
    assert "Inspect the page" in str(normalized[1]["content"])
    assert "Screenshot is available" in str(normalized[1]["content"])


def test_openai_chat_completion_retries_with_string_user_content_when_runtime_requires_it() -> None:
    class _FakeCompletions:
        def __init__(self) -> None:
            self.calls: list[list[dict[str, object]]] = []

        def create(self, *, model, messages, tools, tool_choice, max_tokens):  # noqa: ANN001
            del model, tools, tool_choice, max_tokens
            self.calls.append(messages)
            user_message = messages[1]
            if isinstance(user_message.get("content"), list):
                raise _FakeException(
                    "Error code: 400 - {'error': {'message': 'messages[1].content must be a string'}}",
                    400,
                )
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions()))
    messages = [
        {"role": "system", "content": "system"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Inspect the page"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        },
    ]

    response = openai_provider._create_chat_completion_with_retry(
        client=client,
        model="gpt-4.1-mini",
        messages=messages,
    )

    assert response.choices[0].message.content == "ok"
    assert len(client.chat.completions.calls) == 2
    assert isinstance(client.chat.completions.calls[0][1]["content"], list)
    assert isinstance(client.chat.completions.calls[1][1]["content"], str)
