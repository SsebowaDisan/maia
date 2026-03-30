from __future__ import annotations

from unittest.mock import patch

from api.services.agent.tools.analytics_tools import GA4ReportTool
from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.charts_tools import ChartGenerateTool
from api.services.agent.tools.data_science_tools import (
    DataScienceDeepLearningTrainTool,
    DataScienceModelTrainTool,
    DataScienceProfileTool,
    DataScienceVisualizationTool,
)
from api.services.agent.tools.data_tools import DataAnalysisTool, ReportGenerationTool


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="r1",
        mode="company_agent",
        settings={},
    )


def test_data_analysis_tool_produces_numeric_summary() -> None:
    result = DataAnalysisTool().execute(
        context=_context(),
        prompt="analyze",
        params={"rows": [{"revenue": 100, "cost": 25}, {"revenue": 200, "cost": 75}]},
    )
    assert "Dataset Analysis" in result.content
    assert result.data["row_count"] == 2
    assert "revenue" in result.data["stats"]
    event_types = [event.event_type for event in result.events]
    assert "prepare_request" in event_types
    assert "api_call_started" in event_types
    assert "api_call_completed" in event_types
    assert "normalize_response" in event_types
    _assert_phase1_event_payloads(result, "data.dataset.analyze")


def test_report_generation_tool_persists_latest_report_context() -> None:
    context = _context()
    result = ReportGenerationTool().execute(
        context=context,
        prompt="build report",
        params={"title": "Weekly KPI", "summary": "Pipeline and conversion improved."},
    )
    assert "## Weekly KPI" in result.content
    assert context.settings["__latest_report_title"] == "Weekly KPI"
    assert "Weekly KPI" in context.settings["__latest_report_content"]


def test_report_generation_includes_reference_links_from_recent_web_sources() -> None:
    context = _context()
    context.settings["__latest_web_sources"] = [
        {
            "label": "OpenAI",
            "url": "https://openai.com",
            "metadata": {"excerpt": "Research and deployment of safe AI systems."},
        }
    ]
    result = ReportGenerationTool().execute(
        context=context,
        prompt="build report",
        params={"title": "AI Brief", "summary": "Machine learning overview."},
    )
    assert "### Detailed Analysis" in result.content
    assert "## Sources" in result.content
    assert "[OpenAI](https://openai.com)" in result.content


def test_report_generation_falls_back_to_cited_structure_when_llm_report_is_weak(monkeypatch) -> None:
    context = _context()
    context.settings["__latest_web_sources"] = [
        {
            "label": "Stanford HAI AI Index",
            "url": "https://hai.stanford.edu/ai-index",
            "snippet": "Comprehensive benchmark, adoption, and policy trends across AI and machine learning.",
        },
        {
            "label": "IBM Think: Machine learning",
            "url": "https://www.ibm.com/think/topics/machine-learning",
            "snippet": "Defines supervised, unsupervised, and reinforcement learning with business applications.",
        },
    ]
    monkeypatch.setattr(
        "api.services.agent.tools.data_tools._draft_report_markdown_with_llm",
        lambda **kwargs: "## Weak Draft\n\nShort body with no citations.",
    )
    result = ReportGenerationTool().execute(
        context=context,
        prompt="build a cited machine learning brief",
        params={"title": "ML Brief", "summary": "Explain machine learning clearly with evidence."},
    )
    assert ("### Evidence-backed findings" in result.content) or ("### Detailed Analysis" in result.content)
    assert ("Source era:" in result.content) or ("[Stanford HAI AI Index](https://hai.stanford.edu/ai-index)" in result.content)
    assert "## Sources" in result.content
    assert "[Stanford HAI AI Index](https://hai.stanford.edu/ai-index)" in result.content


def test_report_generation_redacts_delivery_email_from_prompt_context() -> None:
    context = _context()
    context.settings["__task_contract"] = {"delivery_target": "ops@example.com"}
    result = ReportGenerationTool().execute(
        context=context,
        prompt="make research about machine learning and send report to ops@example.com",
        params={"title": "ML Brief"},
    )
    assert "ops@example.com" not in result.content


def test_report_generation_redacts_delivery_email_from_summary_context() -> None:
    context = _context()
    context.settings["__task_contract"] = {"delivery_target": "ops@example.com"}
    result = ReportGenerationTool().execute(
        context=context,
        prompt="generate report",
        params={
            "title": "Research Brief",
            "summary": "Prepare findings and deliver updates to ops@example.com",
        },
    )
    assert "ops@example.com" not in result.content


def test_report_generation_strips_internal_orchestration_seed_text() -> None:
    context = _context()
    result = ReportGenerationTool().execute(
        context=context,
        prompt=(
            "You are executing one workflow stage, not the entire user request.\n"
            "Current stage objective:\n"
            "Write an executive summary.\n\n"
            "Incoming findings from previous stage:\n"
            "Machine learning uses supervised, unsupervised, and reinforcement learning methods.\n\n"
            "Available context and previous outputs:\n"
            "research_output: Modern machine learning systems are trained on data and evaluated for generalization."
        ),
        params={
            "title": "ML Brief",
            "summary": (
                "You are a professional writer. Produce clear, well-structured reports.\n"
                "The researcher agent has completed their work and handed off to you.\n"
                "Summary of their findings:\n"
                "Machine learning is a field of AI focused on learning patterns from data.\n"
                "Your task: Write the final report."
            ),
        },
    )
    assert "You are a professional writer" not in result.content
    assert "handed off to you" not in result.content
    assert "Current stage objective" not in result.content
    assert "Machine learning is a field of AI focused on learning patterns from data." in result.content


def test_report_generation_uses_report_seed_summary_override() -> None:
    context = _context()
    context.settings["__report_seed_summary"] = (
        "Machine learning is a branch of AI that trains models on data to make predictions, "
        "with common categories including supervised, unsupervised, and reinforcement learning."
    )
    result = ReportGenerationTool().execute(
        context=context,
        prompt="Contract objective: write a concise report",
        params={"title": "ML Brief"},
    )
    assert "No summary provided." not in result.content
    assert "Machine learning is a branch of AI" in result.content


def test_chart_generate_tool_returns_artifact_path() -> None:
    result = ChartGenerateTool().execute(
        context=_context(),
        prompt="chart",
        params={"title": "Trend", "labels": ["Mon", "Tue"], "values": [1, 3]},
    )
    assert "Generated" in result.summary
    assert result.data["path"]
    assert result.data["points"] == 2


def test_data_science_profile_tool_profiles_inline_rows() -> None:
    result = DataScienceProfileTool().execute(
        context=_context(),
        prompt="profile",
        params={
            "rows": [
                {"revenue": 100, "cost": 40, "segment": "A"},
                {"revenue": 220, "cost": 80, "segment": "B"},
                {"revenue": 140, "cost": 55, "segment": "A"},
            ]
        },
    )
    assert result.data["row_count"] == 3
    assert "revenue" in result.data["numeric_summary"]
    assert "Data Science Profile" in result.content


def test_data_science_visualization_tool_generates_artifact() -> None:
    result = DataScienceVisualizationTool().execute(
        context=_context(),
        prompt="plot",
        params={
            "rows": [
                {"revenue": 100, "cost": 40},
                {"revenue": 220, "cost": 80},
                {"revenue": 140, "cost": 55},
            ],
            "chart_type": "scatter",
            "x": "revenue",
            "y": "cost",
        },
    )
    assert result.data["path"]
    assert result.data["chart_type"] in {"scatter", "histogram", "line", "bar"}
    event_types = [event.event_type for event in result.events]
    assert "prepare_request" in event_types
    assert "normalize_response" in event_types
    _assert_phase1_event_payloads(result, "data.science.visualize")


def test_data_science_visualization_validates_unknown_columns_gracefully() -> None:
    result = DataScienceVisualizationTool().execute(
        context=_context(),
        prompt="plot",
        params={
            "rows": [
                {"revenue": 100, "cost": 40},
                {"revenue": 220, "cost": 80},
            ],
            "chart_type": "scatter",
            "x": "missing_x",
            "y": "cost",
        },
    )
    assert result.summary == "Visualization validation failed."
    assert result.data.get("available") is False
    assert result.data.get("error_type") == "validation"
    assert any("missing_x" in str(item) for item in result.data.get("validation_errors", []))


def test_data_science_visualization_uses_llm_cleaning_plan(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.agent.tools.data_science.quality.call_json_response",
        lambda **kwargs: {
            "issues": ["Numeric fields are mixed with text values."],
            "cleaning_steps": [
                {
                    "operation": "coerce_numeric",
                    "columns": ["revenue", "cost"],
                    "reason": "Required numeric columns for plotting.",
                },
                {
                    "operation": "drop_rows_with_missing",
                    "columns": ["revenue", "cost"],
                    "reason": "Remove rows that cannot be plotted.",
                },
            ],
        },
    )
    result = DataScienceVisualizationTool().execute(
        context=_context(),
        prompt="plot",
        params={
            "rows": [
                {"revenue": "100", "cost": "40"},
                {"revenue": "N/A", "cost": "80"},
                {"revenue": "220", "cost": "120"},
            ],
            "chart_type": "scatter",
            "x": "revenue",
            "y": "cost",
        },
    )
    assert result.data.get("llm_cleaning_used") is True
    assert isinstance(result.data.get("cleaning_applied"), list)
    assert len(result.data.get("cleaning_applied") or []) >= 1
    assert int(result.data.get("rows_after_cleaning") or 0) <= int(
        result.data.get("rows_before_cleaning") or 0
    )


def test_data_science_visualization_autoselects_multi_series_chart(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.agent.tools.data_science.visualization_planner.call_json_response",
        lambda **kwargs: {
            "chart_type": "line",
            "x": "month",
            "y": "revenue",
            "y_series": ["revenue", "cost"],
            "title": "Revenue vs Cost Trend",
            "reasoning": "Compare monthly movement across two numeric metrics.",
        },
    )
    result = DataScienceVisualizationTool().execute(
        context=_context(),
        prompt="analyze monthly performance with trends",
        params={
            "rows": [
                {"month": "Jan", "revenue": 100, "cost": 40},
                {"month": "Feb", "revenue": 120, "cost": 45},
                {"month": "Mar", "revenue": 160, "cost": 60},
            ],
            "chart_type": "auto",
        },
    )
    plot = result.data.get("plot") or {}
    assert result.data.get("llm_visualization_plan_used") is True
    assert plot.get("chart_type") == "line"
    series = plot.get("series") if isinstance(plot.get("series"), list) else []
    keys = [str(item.get("key")) for item in series if isinstance(item, dict)]
    assert "revenue" in keys
    assert "cost" in keys
    points = plot.get("points") if isinstance(plot.get("points"), list) else []
    assert points and isinstance(points[0], dict)
    assert "revenue" in points[0]
    assert "cost" in points[0]


def _assert_phase1_event_payloads(result, tool_id: str) -> None:
    for event in result.events:
        assert event.data.get("tool_id") == tool_id
        assert event.data.get("scene_surface") == "system"


def test_data_science_profile_emits_phase1_event_contract() -> None:
    result = DataScienceProfileTool().execute(
        context=_context(),
        prompt="profile",
        params={
            "rows": [
                {"revenue": 100, "cost": 40, "segment": "A"},
                {"revenue": 220, "cost": 80, "segment": "B"},
                {"revenue": 140, "cost": 55, "segment": "A"},
            ]
        },
    )
    event_types = [event.event_type for event in result.events]
    assert "prepare_request" in event_types
    assert "api_call_started" in event_types
    assert "api_call_completed" in event_types
    assert "normalize_response" in event_types
    _assert_phase1_event_payloads(result, "data.science.profile")


def test_data_science_ml_train_tool_handles_optional_dependency() -> None:
    result = DataScienceModelTrainTool().execute(
        context=_context(),
        prompt="train model",
        params={
            "rows": [
                {"x1": 1.0, "x2": 3.0, "label": 0},
                {"x1": 2.0, "x2": 5.0, "label": 0},
                {"x1": 3.0, "x2": 7.0, "label": 1},
                {"x1": 4.0, "x2": 8.0, "label": 1},
                {"x1": 5.0, "x2": 9.0, "label": 1},
                {"x1": 6.0, "x2": 10.0, "label": 1},
                {"x1": 7.0, "x2": 11.0, "label": 1},
                {"x1": 8.0, "x2": 12.0, "label": 1},
                {"x1": 9.0, "x2": 13.0, "label": 1},
                {"x1": 10.0, "x2": 14.0, "label": 1},
                {"x1": 11.0, "x2": 15.0, "label": 1},
                {"x1": 12.0, "x2": 16.0, "label": 1},
                {"x1": 13.0, "x2": 17.0, "label": 1},
                {"x1": 14.0, "x2": 18.0, "label": 1},
                {"x1": 15.0, "x2": 19.0, "label": 1},
                {"x1": 16.0, "x2": 20.0, "label": 1},
                {"x1": 17.0, "x2": 21.0, "label": 1},
                {"x1": 18.0, "x2": 22.0, "label": 1},
                {"x1": 19.0, "x2": 23.0, "label": 1},
                {"x1": 20.0, "x2": 24.0, "label": 1},
            ],
            "target": "label",
        },
    )
    if result.data.get("available") is False:
        assert "scikit-learn" in result.content
    else:
        assert "metrics" in result.data
        assert result.data["target"] == "label"
    event_types = [event.event_type for event in result.events]
    assert "prepare_request" in event_types
    assert "normalize_response" in event_types
    if result.data.get("available") is False:
        assert "tool_failed" in event_types
    else:
        assert "api_call_started" in event_types
        assert "api_call_completed" in event_types
    _assert_phase1_event_payloads(result, "data.science.ml.train")


def test_data_science_deep_learning_tool_handles_optional_dependency() -> None:
    rows = [{"x1": float(i), "x2": float(i * 2), "label": int(i >= 20)} for i in range(1, 60)]
    result = DataScienceDeepLearningTrainTool().execute(
        context=_context(),
        prompt="train deep model",
        params={"rows": rows, "target": "label", "epochs": 4},
    )
    if result.data.get("available") is False:
        assert "torch" in result.content
    else:
        assert "metrics" in result.data
        assert result.data["target"] == "label"
    event_types = [event.event_type for event in result.events]
    assert "prepare_request" in event_types
    assert "normalize_response" in event_types
    if result.data.get("available") is False:
        assert "tool_failed" in event_types
    else:
        assert "api_call_started" in event_types
        assert "api_call_completed" in event_types
    _assert_phase1_event_payloads(result, "data.science.deep_learning.train")


class _StubGa4Connector:
    def run_report(self, **kwargs):
        del kwargs
        return {
            "dimensionHeaders": [{"name": "country"}],
            "metricHeaders": [{"name": "sessions"}],
            "rows": [
                {
                    "dimensionValues": [{"value": "BE"}],
                    "metricValues": [{"value": "120"}],
                }
            ],
        }


class _StubRegistry:
    def build(self, connector_id: str, settings: dict | None = None):
        del settings
        assert connector_id == "google_analytics"
        return _StubGa4Connector()


def test_ga4_report_tool_summarizes_rows() -> None:
    with patch("api.services.agent.tools.analytics_tools.get_connector_registry", return_value=_StubRegistry()):
        result = GA4ReportTool().execute(
            context=_context(),
            prompt="ga4",
            params={"metrics": ["sessions"], "dimensions": ["country"]},
        )
    assert result.data["row_count"] == 1
    assert "GA4 report summary" in result.content
