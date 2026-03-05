from __future__ import annotations

from api.services.chat import conversation_naming as naming


def test_normalize_conversation_name_replaces_untitled_without_forcing_icon() -> None:
    result = naming.normalize_conversation_name("Untitled - 2026-03-02 10:00:00")
    assert result == "New chat"


def test_normalize_conversation_name_keeps_plain_title_when_no_icon() -> None:
    result = naming.normalize_conversation_name("Revenue forecast")
    assert result == "Revenue forecast"


def test_normalize_conversation_name_non_latin_title_without_forced_icon() -> None:
    result = naming.normalize_conversation_name("收入预测")
    assert result == "收入预测"


def test_strip_icon_prefix_for_rename_editor() -> None:
    assert naming.strip_icon_prefix("\U0001F4AC Market analysis") == "Market analysis"


def test_normalize_conversation_name_preserves_custom_icon() -> None:
    result = naming.normalize_conversation_name("\U0001F525 Product launch plan")
    assert result == "Product launch plan"


def test_normalize_conversation_name_uses_preferred_icon() -> None:
    result = naming.normalize_conversation_name("Monthly planning", icon="\U0001F4C5")
    assert result == "Monthly planning"


def test_extract_conversation_icon_returns_prefix_icon() -> None:
    assert naming.extract_conversation_icon("\U0001F4CA Revenue analysis") == "\U0001F4CA"


def test_generate_conversation_name_uses_llm_title_and_icon(monkeypatch) -> None:
    monkeypatch.setattr(
        naming,
        "call_json_response",
        lambda **kwargs: {"title": "Quarterly Revenue Forecast", "icon": "\U0001F4C8"},
    )
    result = naming.generate_conversation_name(
        "Please analyze our quarterly revenue trends",
        agent_mode="ask",
    )
    assert result == "Quarterly Revenue"


def test_generate_conversation_name_falls_back_to_message_when_llm_missing(monkeypatch) -> None:
    monkeypatch.setattr(naming, "call_json_response", lambda **kwargs: None)
    result = naming.generate_conversation_name(
        "https://example.com summarize customer churn report for Q1 and Q2",
        agent_mode="company_agent",
    )
    assert len(result) <= naming.MAX_CONVERSATION_NAME_LEN
    assert "Untitled" not in result


def test_generate_conversation_name_no_hardcoded_icon(monkeypatch) -> None:
    monkeypatch.setattr(naming, "call_json_response", lambda **kwargs: None)
    result = naming.generate_conversation_name(
        "Summarize customer churn report for Q1 and Q2",
        agent_mode="ask",
    )
    assert result == "Summarize customer churn"
    assert not result.startswith("\U0001F4AC ")


def test_generate_conversation_name_keeps_short_llm_title(monkeypatch) -> None:
    monkeypatch.setattr(naming, "call_json_response", lambda **kwargs: {"title": "Q2 report"})
    result = naming.generate_conversation_name(
        "Please prepare Q2 report and next quarter planning milestones",
        agent_mode="ask",
    )
    assert result == "Q2 report"


def test_generate_conversation_name_enforces_max_25_chars(monkeypatch) -> None:
    monkeypatch.setattr(naming, "call_json_response", lambda **kwargs: {"title": "A very long conversation title that exceeds twenty five chars"})
    result = naming.generate_conversation_name(
        "Please prepare a long report",
        agent_mode="ask",
    )
    assert len(result) <= 25


def test_normalize_conversation_name_keeps_word_on_boundary_cut() -> None:
    result = naming.normalize_conversation_name("Summarize customer churn report for Q1 and Q2")
    assert result == "Summarize customer churn"


def test_is_legacy_fallback_icon() -> None:
    assert naming.is_legacy_fallback_icon("\U0001F4AC")
    assert not naming.is_legacy_fallback_icon("\U0001F4C8")
