from api.schemas import ChatRequest
from api.services.agent.models import AgentSource
from api.services.agent.orchestration.answer_builder import compose_professional_answer


def test_value_add_section_is_included_when_evidence_support_is_strong() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(message="Summarize verified insights and next opportunities.", agent_mode="company_agent"),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={"__show_response_diagnostics": True},
        verification_report={
            "score": 92.0,
            "grade": "strong",
            "checks": [{"name": "Claim support coverage", "status": "pass", "detail": "Good coverage"}],
            "claim_assessments": [
                {
                    "claim": "Axon Group is headquartered in Brussels, Belgium.",
                    "supported": True,
                    "score": 0.84,
                    "evidence_source": "Source A",
                },
                {
                    "claim": "Axon Group provides digital transformation services in manufacturing.",
                    "supported": True,
                    "score": 0.79,
                    "evidence_source": "Source B",
                },
            ],
            "contradictions": [],
            "evidence_units": [
                {"source": "Source A", "url": "https://example.com/about", "text": "Brussels headquarters"},
                {"source": "Source B", "url": "https://example.com/services", "text": "Digital transformation services"},
            ],
        },
    )
    assert "## Evidence-Backed Value Add" in answer
    assert "Source: https://example.com/about" in answer or "Source: https://example.com/services" in answer
    assert "confidence:" in answer
    assert "## Evidence Citations" in answer
    assert "https://example.com/about" in answer


def test_value_add_section_is_hidden_when_contradictions_exist() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(message="Summarize verified insights.", agent_mode="company_agent"),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={"__show_response_diagnostics": True},
        verification_report={
            "score": 61.0,
            "grade": "fair",
            "checks": [{"name": "Contradiction scan", "status": "warn", "detail": "Potential conflicts"}],
            "claim_assessments": [
                {
                    "claim": "Company has 100 employees.",
                    "supported": True,
                    "score": 0.82,
                    "evidence_source": "Source A",
                },
                {
                    "claim": "Company has 250 employees.",
                    "supported": True,
                    "score": 0.83,
                    "evidence_source": "Source B",
                },
            ],
            "contradictions": [{"type": "numeric_mismatch"}],
            "evidence_units": [
                {"source": "Source A", "url": "https://example.com/a", "text": "100 employees"},
                {"source": "Source B", "url": "https://example.com/b", "text": "250 employees"},
            ],
        },
    )
    assert "## Evidence-Backed Value Add" not in answer


def test_value_add_section_is_hidden_when_support_coverage_is_low() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(message="Summarize verified insights.", agent_mode="company_agent"),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={"__show_response_diagnostics": True},
        verification_report={
            "score": 55.0,
            "grade": "weak",
            "checks": [{"name": "Claim support coverage", "status": "warn", "detail": "Low support"}],
            "claim_assessments": [
                {
                    "claim": "The company has expanded to 12 countries.",
                    "supported": False,
                    "score": 0.12,
                    "evidence_source": "",
                },
                {
                    "claim": "The company has 90% growth year over year.",
                    "supported": True,
                    "score": 0.44,
                    "evidence_source": "Source A",
                },
            ],
            "contradictions": [],
            "evidence_units": [
                {"source": "Source A", "url": "https://example.com/a", "text": "Limited growth data"},
            ],
        },
    )
    assert "## Evidence-Backed Value Add" not in answer


def test_answer_always_includes_evidence_citations_with_deduplicated_sources() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(message="Summarize findings.", agent_mode="company_agent"),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[
            AgentSource(
                source_type="web",
                label="Company About",
                url="https://example.com/about",
                metadata={"snippet": "Company profile details."},
            ),
            AgentSource(
                source_type="web",
                label="Company About duplicate",
                url="https://example.com/about",
                metadata={"snippet": "Duplicate row should not create a second citation."},
            ),
        ],
        next_steps=[],
        runtime_settings={},
        verification_report=None,
    )
    assert "## Evidence Citations" in answer
    assert "- [1] [Company About](https://example.com/about)" in answer
    assert "Duplicate row should not create a second citation." not in answer


def test_answer_includes_evidence_citations_section_when_no_sources_exist() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(message="Summarize findings.", agent_mode="company_agent"),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={},
        verification_report=None,
    )
    assert "## Evidence Citations" in answer
    assert "No external evidence sources were captured in this run" in answer
