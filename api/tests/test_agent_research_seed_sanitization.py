from api.services.agent.orchestration.step_planner_sections import research as module


def test_seeded_search_terms_from_settings_ignores_instructional_constraints() -> None:
    settings = {
        "__workflow_stage_primary_topic": "machine learning",
        "__research_search_terms": [
            "machine learning enterprise adoption",
            "Brief must be 1000–1500 characters unless compression would harm clarity or citation integrity",
            "Every [n] must resolve to a unique numbered citation",
        ],
    }

    assert module._seeded_search_terms_from_settings(settings) == [
        "machine learning",
        "machine learning enterprise adoption",
    ]
