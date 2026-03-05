from __future__ import annotations

from api.services.agent.tools.google_target_resolution import (
    resolve_ga4_reference,
    resolve_sheet_reference,
)


def test_resolve_sheet_reference_from_alias_in_prompt() -> None:
    settings = {
        "agent.google_workspace_link_aliases": {
            "Quarterly Traffic": {
                "alias": "Quarterly Traffic",
                "resource_type": "google_sheet",
                "resource_id": "17xYzAbCdEfGhIjKlMnOpQrStUvWx123456",
                "canonical_url": "https://docs.google.com/spreadsheets/d/17xYzAbCdEfGhIjKlMnOpQrStUvWx123456/edit",
            }
        }
    }
    ref = resolve_sheet_reference(
        prompt="append the KPI rows to Quarterly Traffic",
        params={},
        settings=settings,
    )
    assert ref is not None
    assert ref.resource_type == "google_sheet"
    assert ref.resource_id == "17xYzAbCdEfGhIjKlMnOpQrStUvWx123456"


def test_resolve_sheet_reference_from_link_param() -> None:
    ref = resolve_sheet_reference(
        prompt="",
        params={
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/17xYzAbCdEfGhIjKlMnOpQrStUvWx123456/edit"
        },
        settings={},
    )
    assert ref is not None
    assert ref.resource_type == "google_sheet"


def test_resolve_ga4_reference_from_alias_param() -> None:
    settings = {
        "agent.google_workspace_link_aliases": {
            "main ga4": {
                "alias": "Main GA4",
                "resource_type": "ga4_property",
                "resource_id": "123456789",
                "canonical_url": "https://analytics.google.com/analytics/web/#/p123456789",
            }
        }
    }
    ref = resolve_ga4_reference(
        prompt="run report",
        params={"property_alias": "main ga4"},
        settings=settings,
    )
    assert ref is not None
    assert ref.resource_type == "ga4_property"
    assert ref.resource_id == "123456789"


def test_resolve_ga4_reference_from_prompt_link() -> None:
    ref = resolve_ga4_reference(
        prompt="check this property https://analytics.google.com/analytics/web/#/p123456789/reports",
        params={},
        settings={},
    )
    assert ref is not None
    assert ref.resource_type == "ga4_property"
    assert ref.resource_id == "123456789"
