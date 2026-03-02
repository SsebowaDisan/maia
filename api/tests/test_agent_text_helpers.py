from __future__ import annotations

from api.services.agent.orchestration.text_helpers import extract_action_artifact_metadata


def test_extract_action_artifact_metadata_includes_plot_payload() -> None:
    metadata = extract_action_artifact_metadata(
        {
            "plot": {
                "kind": "chart",
                "chart_type": "line",
                "title": "Revenue trend",
                "x": "month",
                "y": "revenue",
                "points": [
                    {"x": "Jan", "y": 10},
                    {"x": "Feb", "y": 12.5},
                ],
            }
        },
        step=2,
    )
    assert metadata["step"] == 2
    assert "plot" in metadata
    plot = metadata["plot"]
    assert plot["kind"] == "chart"
    assert plot["chart_type"] == "line"
    assert len(plot["points"]) == 2


def test_extract_action_artifact_metadata_keeps_multi_series_plot() -> None:
    metadata = extract_action_artifact_metadata(
        {
            "plot": {
                "kind": "chart",
                "chart_type": "line",
                "title": "Revenue vs Cost",
                "x": "month",
                "y": "revenue",
                "series": [
                    {"key": "revenue", "label": "Revenue", "type": "line"},
                    {"key": "cost", "label": "Cost", "type": "line"},
                ],
                "points": [
                    {"x": "Jan", "revenue": 100, "cost": 40},
                    {"x": "Feb", "revenue": 120, "cost": 45},
                ],
            }
        },
        step=3,
    )
    plot = metadata["plot"]
    assert plot["series"][0]["key"] == "revenue"
    assert plot["series"][1]["key"] == "cost"
    assert plot["points"][0]["revenue"] == 100
    assert plot["points"][0]["cost"] == 40


def test_extract_action_artifact_metadata_ignores_invalid_plot_payload() -> None:
    metadata = extract_action_artifact_metadata(
        {
            "plot": {
                "kind": "table",
                "chart_type": "line",
                "points": [{"x": "A", "y": 1}],
            }
        },
        step=1,
    )
    assert metadata == {"step": 1}
