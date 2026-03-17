from __future__ import annotations

from api.services.computer_use import runtime_config
from api.services.computer_use.runtime_health import RuntimeHealthResult


def test_resolve_effective_model_prefers_explicit() -> None:
    model, source = runtime_config.resolve_effective_model(
        explicit_model="ollama::qwen2.5vl:7b",
        user_settings={"agent.computer_use_model": "claude-opus-4-6"},
    )
    assert model == "ollama::qwen2.5vl:7b"
    assert source == "explicit"


def test_resolve_effective_model_uses_ollama_setting_before_openai_chat_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-4o")
    monkeypatch.delenv("COMPUTER_USE_MODEL", raising=False)
    monkeypatch.setattr(runtime_config, "active_ollama_model", lambda: None)

    model, source = runtime_config.resolve_effective_model(
        user_settings={"agent.ollama.default_model": "qwen2.5vl:7b"}
    )
    assert model == "qwen2.5vl:7b"
    assert source == "settings:agent.ollama.default_model"


def test_resolve_effective_model_falls_back_to_open_source_default(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    monkeypatch.delenv("COMPUTER_USE_MODEL", raising=False)
    monkeypatch.setattr(runtime_config, "active_ollama_model", lambda: None)

    model, source = runtime_config.resolve_effective_model(user_settings={})
    assert model == runtime_config.DEFAULT_OPEN_SOURCE_MODEL
    assert source == "default:open_source"


def test_resolve_openai_base_url_uses_ollama_for_oss_model(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    base_url, source = runtime_config.resolve_openai_base_url(
        model="qwen2.5vl:7b",
        user_settings={"agent.ollama.base_url": "http://localhost:11434"},
    )
    assert base_url == "http://localhost:11434/v1"
    assert source.startswith("ollama:")


def test_validate_runtime_requirements_fails_for_claude_without_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    ok, error = runtime_config.validate_runtime_requirements(
        model="claude-opus-4-6",
        user_settings={},
    )
    assert not ok
    assert "ANTHROPIC_API_KEY" in error


def test_normalize_model_name_strips_ollama_prefix() -> None:
    assert runtime_config.normalize_model_name("ollama::qwen2.5vl:7b") == "qwen2.5vl:7b"


def test_validate_runtime_requirements_checks_ollama_health(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        runtime_config,
        "check_ollama_runtime",
        lambda **kwargs: RuntimeHealthResult(ok=False, error="runtime down"),
    )

    ok, error = runtime_config.validate_runtime_requirements(
        model="qwen2.5vl:7b",
        user_settings={"agent.ollama.base_url": "http://127.0.0.1:11434"},
    )
    assert not ok
    assert error == "runtime down"


def test_validate_runtime_requirements_passes_with_healthy_ollama(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        runtime_config,
        "check_ollama_runtime",
        lambda **kwargs: RuntimeHealthResult(ok=True, error=""),
    )

    ok, error = runtime_config.validate_runtime_requirements(
        model="qwen2.5vl:7b",
        user_settings={"agent.ollama.base_url": "http://127.0.0.1:11434"},
    )
    assert ok
    assert error == ""
