from api.services.agent.tools import research_web_tool_stream as module


def test_primary_topic_from_settings_prefers_stage_topic() -> None:
    settings = {
        "__workflow_stage_primary_topic": "machine learning",
        "__research_search_terms": ["ignored fallback"],
    }

    assert module._primary_topic_from_settings(settings) == "machine learning"


def test_prompt_scaffold_detection_flags_stage_prompt() -> None:
    prompt = (
        "You are responsible for the role Research Specialist. Execute only your assigned step with evidence and clear handoff. "
        "Current step focus: Conduct research on machine learning to gather key insights and findings."
    )

    assert module._looks_like_prompt_scaffold(prompt) is True
