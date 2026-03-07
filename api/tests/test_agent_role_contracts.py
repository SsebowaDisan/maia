from __future__ import annotations

from api.services.agent.orchestration.agent_roles import (
    agent_role_description,
    agent_role_label,
    is_agent_role,
    list_agent_roles,
    normalize_agent_role,
)
from api.services.agent.orchestration.role_contracts import (
    get_role_contract,
    list_role_contracts,
    resolve_owner_role_for_tool,
    role_allows_tool,
)


def test_agent_role_catalog_is_stable() -> None:
    assert list_agent_roles() == (
        "conductor",
        "planner",
        "research",
        "browser",
        "document",
        "analyst",
        "writer",
        "verifier",
        "safety",
    )


def test_role_normalization_and_validation() -> None:
    assert is_agent_role(" planner ")
    assert not is_agent_role("unknown")
    assert normalize_agent_role(" WRITER ") == "writer"
    assert normalize_agent_role("unknown") == "conductor"


def test_role_labels_and_descriptions_are_defined() -> None:
    assert agent_role_label("browser") == "Browser"
    assert "interaction" in agent_role_description("browser").lower()


def test_all_roles_have_contracts() -> None:
    contracts = list_role_contracts()
    assert len(contracts) == len(list_agent_roles())
    assert {item.role for item in contracts} == set(list_agent_roles())


def test_writer_contract_allows_report_tool() -> None:
    contract = get_role_contract("writer")
    assert contract.role == "writer"
    assert role_allows_tool(role="writer", tool_id="report.generate")
    assert role_allows_tool(role="writer", tool_id="workspace.docs.research_notes")
    assert not role_allows_tool(role="writer", tool_id="browser.playwright.inspect")


def test_resolve_owner_role_for_tool_uses_contracts() -> None:
    assert resolve_owner_role_for_tool("browser.playwright.inspect") == "browser"
    assert resolve_owner_role_for_tool("documents.highlight.extract") == "document"
    assert resolve_owner_role_for_tool("data.science.profile") == "analyst"
    assert resolve_owner_role_for_tool("report.generate") == "writer"
    assert resolve_owner_role_for_tool("marketing.web_research") == "research"


def test_resolve_owner_role_for_tool_uses_default_for_unknown() -> None:
    assert resolve_owner_role_for_tool("unknown.tool.id") == "research"
    assert resolve_owner_role_for_tool("unknown.tool.id", default_role="writer") == "writer"
    assert resolve_owner_role_for_tool("") == "research"
