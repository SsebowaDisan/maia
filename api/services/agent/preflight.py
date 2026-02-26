from __future__ import annotations

import os
from typing import Any

from maia.integrations.gmail_dwd import load_gmail_dwd_config


def _env(name: str) -> str:
    return str(os.getenv(name, "")).strip()


def run_preflight_checks(
    *,
    requires_delivery: bool,
    requires_web_inspection: bool,
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    if requires_delivery:
        try:
            load_gmail_dwd_config()
            checks.append(
                {
                    "name": "mailer_dwd_config",
                    "status": "pass",
                    "detail": "DWD mailer configuration is available.",
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": "mailer_dwd_config",
                    "status": "warn",
                    "detail": (
                        "DWD mailer configuration missing or invalid. "
                        f"Delivery may fail: {exc}"
                    ),
                }
            )

    if requires_web_inspection:
        has_brave_key = bool(_env("BRAVE_SEARCH_API_KEY"))
        checks.append(
            {
                "name": "web_search_provider",
                "status": "pass" if has_brave_key else "warn",
                "detail": (
                    "Brave Search API key detected."
                    if has_brave_key
                    else "BRAVE_SEARCH_API_KEY not set; web search may fallback or return limited results."
                ),
            }
        )

    if not checks:
        checks.append(
            {
                "name": "preflight_baseline",
                "status": "pass",
                "detail": "No high-risk prerequisites required for this request.",
            }
        )

    return checks

