from __future__ import annotations

from api.services.chat import conversation_naming as naming


def test_normalize_conversation_name_replaces_untitled() -> None:
    result = naming.normalize_conversation_name("Untitled - 2026-03-02 10:00:00")
    assert result == "💬 New chat"


def test_normalize_conversation_name_adds_icon_prefix() -> None:
    result = naming.normalize_conversation_name("Revenue forecast")
    assert result.startswith("💬 ")
    assert result.endswith("Revenue forecast")


def test_normalize_conversation_name_non_latin_still_gets_default_icon() -> None:
    result = naming.normalize_conversation_name("收入预测")
    assert result.startswith("💬 ")
    assert result.endswith("收入预测")


def test_strip_icon_prefix_for_rename_editor() -> None:
    assert naming.strip_icon_prefix("💬 Market analysis") == "Market analysis"


def test_normalize_conversation_name_preserves_custom_icon() -> None:
    result = naming.normalize_conversation_name("🔥 Product launch plan")
    assert result == "🔥 Product launch plan"


def test_normalize_conversation_name_uses_preferred_icon() -> None:
    result = naming.normalize_conversation_name("Monthly planning", icon="📅")
    assert result == "📅 Monthly planning"


def test_extract_conversation_icon_returns_prefix_icon() -> None:
    assert naming.extract_conversation_icon("📊 Revenue analysis") == "📊"


def test_generate_conversation_name_uses_llm_title_and_icon(monkeypatch) -> None:
    monkeypatch.setattr(
        naming,
        "call_json_response",
        lambda **kwargs: {"title": "Quarterly Revenue Forecast", "icon": "📈"},
    )
    monkeypatch.setattr(naming, "call_text_response", lambda **kwargs: "")
    result = naming.generate_conversation_name(
        "Please analyze our quarterly revenue trends",
        agent_mode="ask",
    )
    assert result == "📈 Quarterly Revenue Forecast"


def test_generate_conversation_name_falls_back_when_llm_empty(monkeypatch) -> None:
    monkeypatch.setattr(naming, "call_json_response", lambda **kwargs: None)
    monkeypatch.setattr(naming, "call_text_response", lambda **kwargs: "📉")
    result = naming.generate_conversation_name(
        "https://example.com summarize customer churn report for Q1 and Q2",
        agent_mode="company_agent",
    )
    assert result.startswith("📉 ")
    assert "Untitled" not in result
    assert len(result) > 2
