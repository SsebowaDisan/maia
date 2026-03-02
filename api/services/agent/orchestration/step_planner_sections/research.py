from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.llm_research_blueprint import build_research_blueprint
from api.services.agent.planner import PlannedStep, is_deep_research_request


@dataclass(slots=True, frozen=True)
class ResearchBlueprint:
    deep_research_mode: bool
    highlight_color: str
    planned_search_terms: list[str]
    planned_keywords: list[str]


def build_research_plan(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
) -> ResearchBlueprint:
    deep_research_mode = is_deep_research_request(request)
    highlight_color = (
        " ".join(str(settings.get("agent.default_highlight_color") or "yellow").split())
        .strip()
        .lower()
    )
    if highlight_color not in {"yellow", "green"}:
        highlight_color = "yellow"

    research_blueprint = build_research_blueprint(
        message=request.message,
        agent_goal=request.agent_goal,
        min_keywords=10,
    )
    planned_search_terms = [
        str(item).strip()
        for item in (
            research_blueprint.get("search_terms")
            if isinstance(research_blueprint, dict)
            else []
        )
        if str(item).strip()
    ]
    planned_keywords = [
        str(item).strip()
        for item in (
            research_blueprint.get("keywords") if isinstance(research_blueprint, dict) else []
        )
        if str(item).strip()
    ]
    return ResearchBlueprint(
        deep_research_mode=deep_research_mode,
        highlight_color=highlight_color,
        planned_search_terms=planned_search_terms,
        planned_keywords=planned_keywords,
    )


def normalize_step_parameters(
    *,
    steps: list[PlannedStep],
    planned_search_terms: list[str],
    planned_keywords: list[str],
    highlight_color: str,
) -> list[PlannedStep]:
    normalized_steps: list[PlannedStep] = []
    for step in steps:
        params = dict(step.params)
        if step.tool_id == "marketing.web_research" and planned_search_terms:
            params["query"] = planned_search_terms[0]
            if len(planned_search_terms) > 1:
                params.setdefault("query_variants", planned_search_terms[1:4])
        if step.tool_id in ("browser.playwright.inspect", "documents.highlight.extract"):
            params.setdefault("highlight_color", highlight_color)
        if step.tool_id == "documents.highlight.extract" and planned_keywords:
            params.setdefault("words", planned_keywords[:12])
        if step.tool_id == "docs.create":
            params.setdefault("include_copied_highlights", True)
        normalized_steps.append(
            PlannedStep(tool_id=step.tool_id, title=step.title, params=params)
        )
    return normalized_steps


def ensure_company_agent_highlight_step(
    *,
    request: ChatRequest,
    steps: list[PlannedStep],
    highlight_color: str,
    planned_keywords: list[str],
) -> list[PlannedStep]:
    if request.agent_mode != "company_agent":
        return steps
    if any(step.tool_id == "documents.highlight.extract" for step in steps):
        return steps

    insert_at = len(steps)
    for idx, step in enumerate(steps):
        if step.tool_id in (
            "browser.playwright.inspect",
            "marketing.web_research",
            "web.extract.structured",
            "web.dataset.adapter",
        ):
            insert_at = idx + 1
            break
    steps.insert(
        insert_at,
        PlannedStep(
            tool_id="documents.highlight.extract",
            title="Highlight words in selected files",
            params={"highlight_color": highlight_color, "words": planned_keywords[:12]},
        ),
    )
    return steps
