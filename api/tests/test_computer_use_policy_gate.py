from __future__ import annotations

from api.services.computer_use.policy_gate import evaluate_task_policy, get_policy_snapshot


def test_policy_enforce_mode_blocks_matching_term(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_COMPUTER_USE_POLICY_MODE", "enforce")
    monkeypatch.setenv("MAIA_COMPUTER_USE_BLOCKED_TASK_TERMS", "steal credentials, bypass 2fa")

    decision = evaluate_task_policy("Open the admin page and steal credentials from the form.")

    assert decision.allowed is False
    assert decision.mode == "enforce"
    assert "blocked policy terms" in decision.reason.lower()
    assert "steal credentials" in decision.matched_terms


def test_policy_audit_mode_warns_but_allows(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_COMPUTER_USE_POLICY_MODE", "audit")
    monkeypatch.setenv("MAIA_COMPUTER_USE_BLOCKED_TASK_TERMS", "exfiltrate")

    decision = evaluate_task_policy("Try to exfiltrate all records.")

    assert decision.allowed is True
    assert decision.mode == "audit"
    assert "exfiltrate" in decision.reason.lower()


def test_policy_off_mode_allows_even_if_term_matches(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_COMPUTER_USE_POLICY_MODE", "off")
    monkeypatch.setenv("MAIA_COMPUTER_USE_BLOCKED_TASK_TERMS", "ransomware")

    decision = evaluate_task_policy("simulate ransomware response procedure")

    assert decision.allowed is True
    assert decision.mode == "off"
    assert decision.reason == ""
    assert decision.matched_terms == ()


def test_policy_blocks_excessive_task_length(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_COMPUTER_USE_POLICY_MODE", "enforce")
    monkeypatch.setenv("MAIA_COMPUTER_USE_MAX_TASK_CHARS", "20")
    monkeypatch.setenv("MAIA_COMPUTER_USE_BLOCKED_TASK_TERMS", "")

    decision = evaluate_task_policy("A" * 24)

    assert decision.allowed is False
    assert "too long" in decision.reason.lower()
    assert decision.max_task_chars == 20


def test_policy_snapshot_reports_resolved_values(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_COMPUTER_USE_POLICY_MODE", "audit")
    monkeypatch.setenv("MAIA_COMPUTER_USE_MAX_TASK_CHARS", "1234")
    monkeypatch.setenv("MAIA_COMPUTER_USE_BLOCKED_TASK_TERMS", "alpha,beta")

    snapshot = get_policy_snapshot()

    assert snapshot["mode"] == "audit"
    assert snapshot["max_task_chars"] == 1234
    assert snapshot["blocked_terms_count"] == 2
    assert snapshot["blocked_terms_preview"] == ["alpha", "beta"]
