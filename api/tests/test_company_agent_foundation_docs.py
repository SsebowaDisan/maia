from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def _line_count(rel_path: str) -> int:
    return len((ROOT / rel_path).read_text(encoding="utf-8").splitlines())


def test_foundation_docs_exist_and_cover_required_sections() -> None:
    scope_doc = _read("docs/company_agent/strategic_scope_and_governance_alignment.md")
    acceptance_doc = _read("docs/company_agent/acceptance_criteria_catalog.md")
    architecture_doc = _read("docs/company_agent/architecture_and_data_strategy_blueprint.md")
    integration_doc = _read("docs/company_agent/integration_and_runtime_baseline.md")

    assert "Stakeholder Ownership Matrix" in scope_doc
    assert "Governance Baseline" in scope_doc
    assert "Replay-Safe State Transition Model" in architecture_doc
    assert "Data Strategy" in architecture_doc
    assert "Integration Baseline" in integration_doc
    assert "Baseline Acceptance Validation" in integration_doc
    assert "Server-Side Mailer Service" in acceptance_doc
    assert "Modes and Personalization Framework" in acceptance_doc


def test_roadmap_and_foundation_docs_respect_file_loc_rule() -> None:
    tracked = [
        "docs/company_agent_end_to_end_roadmap.md",
        "docs/company_agent/strategic_scope_and_governance_alignment.md",
        "docs/company_agent/acceptance_criteria_catalog.md",
        "docs/company_agent/architecture_and_data_strategy_blueprint.md",
        "docs/company_agent/integration_and_runtime_baseline.md",
    ]
    for rel_path in tracked:
        assert _line_count(rel_path) <= 500, f"{rel_path} exceeds 500 LOC"

