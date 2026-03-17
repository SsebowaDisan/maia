from __future__ import annotations

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

