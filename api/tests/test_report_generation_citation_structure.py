from __future__ import annotations

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.data_tools import ReportGenerationTool
from api.services.agent.tools.report_utils import _redact_delivery_targets


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="r1",
        mode="company_agent",
        settings={},
    )


def test_report_generation_includes_sources_section_from_recent_web_sources() -> None:
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
        {
            "label": "Nature Machine Intelligence",
            "url": "https://www.nature.com/natmachintell/",
            "snippet": "Peer-reviewed research and review coverage across machine learning topics.",
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
    assert "### Evidence-backed findings" in result.content
    assert "Source era:" in result.content
    assert "## Sources" in result.content
    assert "[Stanford HAI AI Index](https://hai.stanford.edu/ai-index)" in result.content


def test_redact_delivery_targets_preserves_markdown_line_breaks() -> None:
    text = "## Title\n\n### Executive Summary\nSend to ops@example.com.\n\n## Sources\n- [Example](https://example.com)"
    cleaned = _redact_delivery_targets(text, targets=["ops@example.com"])
    assert "ops@example.com" not in cleaned
    assert "\n### Executive Summary\n" in cleaned
    assert "\n## Sources\n" in cleaned
