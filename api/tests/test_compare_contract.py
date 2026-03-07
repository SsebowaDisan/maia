from __future__ import annotations

from api.services.agent.execution.compare_contract import apply_compare_contract


def test_apply_compare_contract_normalizes_compare_payload() -> None:
    payload = apply_compare_contract(
        event_type="pdf_compare_regions",
        data={
            "scene_surface": "document",
            "compare_region_a": "Q3 operating margin 18%",
            "compare_region_b": "Q4 operating margin 22%",
            "compare_verdict": "Q4 stronger margin",
            "compare_confidence": 0.81,
        },
    )
    assert payload["compare_mode_enabled"] is True
    assert payload["compare_left"] == "Q3 operating margin 18%"
    assert payload["compare_right"] == "Q4 operating margin 22%"
    assert payload["compare_mode"]["surface"] == "document"
    assert payload["compare_mode"]["verdict"] == "Q4 stronger margin"
    assert payload["compare_mode"]["confidence"] == 0.81


def test_apply_compare_contract_uses_embedded_compare_mode() -> None:
    payload = apply_compare_contract(
        event_type="tool_progress",
        data={
            "compare_mode": {
                "left": "Source A says 31%",
                "right": "Source B says 29%",
                "surface": "website",
            }
        },
    )
    assert payload["compare_mode_enabled"] is True
    assert payload["compare_left"] == "Source A says 31%"
    assert payload["compare_right"] == "Source B says 29%"
    assert payload["compare_mode"]["surface"] == "website"
