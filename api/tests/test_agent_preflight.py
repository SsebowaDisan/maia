from __future__ import annotations

from unittest.mock import patch

from api.services.agent.preflight import run_preflight_checks


def test_preflight_baseline_when_no_special_requirements() -> None:
    checks = run_preflight_checks(requires_delivery=False, requires_web_inspection=False)
    assert checks
    assert checks[0]["status"] == "pass"


def test_preflight_warns_when_web_search_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    checks = run_preflight_checks(requires_delivery=False, requires_web_inspection=True)
    assert any(check["name"] == "web_search_provider" and check["status"] == "warn" for check in checks)


def test_preflight_warns_when_dwd_config_missing() -> None:
    with patch("api.services.agent.preflight.load_gmail_dwd_config", side_effect=RuntimeError("missing")):
        checks = run_preflight_checks(requires_delivery=True, requires_web_inspection=False)
    assert any(check["name"] == "mailer_dwd_config" and check["status"] == "warn" for check in checks)

