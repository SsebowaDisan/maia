from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.llm_research_blueprint import build_research_blueprint
from api.services.agent.planner_helpers import infer_intent_signals_from_text
from api.services.agent.planner import PlannedStep, is_deep_research_request

GA_TOOL_IDS = {
    "analytics.ga4.report",
    "analytics.ga4.full_report",
    "business.ga4_kpi_sheet_report",
}


@dataclass(slots=True, frozen=True)
class ResearchBlueprint:
    deep_research_mode: bool
    depth_tier: str
    highlight_color: str
    planned_search_terms: list[str]
    planned_keywords: list[str]
    max_query_variants: int
    results_per_query: int
    fused_top_k: int
    max_live_inspections: int
    min_unique_sources: int
    web_search_budget: int
    max_file_sources: int
    max_file_chunks: int
    max_file_scan_pages: int
    simple_explanation_required: bool


def _as_bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(low, min(high, parsed))


def _keyword_floor_for_request(request: ChatRequest, *, settings: dict[str, Any]) -> int:
    explicit_floor = settings.get("__research_min_keywords")
    try:
        explicit_floor_int = int(explicit_floor)
    except Exception:
        explicit_floor_int = 0
    if explicit_floor_int > 0:
        return max(4, min(explicit_floor_int, 40))
    return 10


def _has_selected_files(request: ChatRequest) -> bool:
    for selection in request.index_selection.values():
        file_ids = getattr(selection, "file_ids", []) or []
        if any(str(file_id).strip() for file_id in file_ids):
            return True
    for attachment in request.attachments:
        if str(getattr(attachment, "file_id", "") or "").strip():
            return True
    return False


def _has_attached_files(request: ChatRequest) -> bool:
    for attachment in request.attachments:
        if str(getattr(attachment, "file_id", "") or "").strip():
            return True
    return False


def _should_auto_insert_highlight_step(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
) -> bool:
    intent = infer_intent_signals_from_text(
        message=request.message,
        agent_goal=request.agent_goal,
    )
    deep_search_mode = str(request.agent_mode or "").strip().lower() == "deep_search" or bool(
        settings.get("__deep_search_enabled")
    )
    if deep_search_mode:
        prompt_scoped_pdfs = bool(settings.get("__deep_search_prompt_scoped_pdfs"))
        user_selected_files = bool(settings.get("__deep_search_user_selected_files"))
        if prompt_scoped_pdfs or user_selected_files or _has_attached_files(request):
            return True
        return False
    if bool(intent.get("wants_highlight_words")):
        return True
    if _has_selected_files(request) and bool(intent.get("wants_file_scope")):
        return True
    return False


def build_research_plan(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
) -> ResearchBlueprint:
    depth_tier = str(settings.get("__research_depth_tier") or "").strip().lower() or "standard"
    deep_research_mode = depth_tier in {"deep_research", "deep_analytics"} or is_deep_research_request(request)
    highlight_color = (
        " ".join(str(settings.get("agent.default_highlight_color") or "yellow").split())
        .strip()
        .lower()
    )
    if highlight_color not in {"yellow", "green"}:
        highlight_color = "yellow"

    target_query_variants = _as_bounded_int(
        settings.get("__research_max_query_variants"),
        default=4,
        low=2,
        high=20,
    )
    research_blueprint = build_research_blueprint(
        message=request.message,
        agent_goal=request.agent_goal,
        min_keywords=_keyword_floor_for_request(request, settings=settings),
        min_search_terms=max(4, min(target_query_variants, 20)),
        llm_only=bool(settings.get("__llm_only_keyword_generation", True)),
        llm_strict=bool(settings.get("__llm_only_keyword_generation_strict", False)),
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
        depth_tier=depth_tier,
        highlight_color=highlight_color,
        planned_search_terms=planned_search_terms,
        planned_keywords=planned_keywords,
        max_query_variants=_as_bounded_int(
            settings.get("__research_max_query_variants"),
            default=target_query_variants,
            low=2,
            high=20,
        ),
        results_per_query=_as_bounded_int(
            settings.get("__research_results_per_query"),
            default=8,
            low=4,
            high=25,
        ),
        fused_top_k=_as_bounded_int(
            settings.get("__research_fused_top_k"),
            default=24,
            low=8,
            high=220,
        ),
        max_live_inspections=_as_bounded_int(
            settings.get("__research_max_live_inspections"),
            default=4,
            low=2,
            high=40,
        ),
        min_unique_sources=_as_bounded_int(
            settings.get("__research_min_unique_sources"),
            default=8,
            low=3,
            high=200,
        ),
        web_search_budget=_as_bounded_int(
            settings.get("__research_web_search_budget"),
            default=(
                _as_bounded_int(
                    settings.get("__research_max_query_variants"),
                    default=4,
                    low=2,
                    high=20,
                )
                * _as_bounded_int(
                    settings.get("__research_results_per_query"),
                    default=8,
                    low=4,
                    high=25,
                )
            ),
            low=20,
            high=350,
        ),
        max_file_sources=_as_bounded_int(
            settings.get("__file_research_max_sources"),
            default=40,
            low=3,
            high=240,
        ),
        max_file_chunks=_as_bounded_int(
            settings.get("__file_research_max_chunks"),
            default=260,
            low=40,
            high=3000,
        ),
        max_file_scan_pages=_as_bounded_int(
            settings.get("__file_research_max_scan_pages"),
            default=40,
            low=8,
            high=300,
        ),
        simple_explanation_required=bool(settings.get("__simple_explanation_required")),
    )


def normalize_step_parameters(
    *,
    steps: list[PlannedStep],
    planned_search_terms: list[str],
    planned_keywords: list[str],
    highlight_color: str,
    research_plan: ResearchBlueprint,
) -> list[PlannedStep]:
    normalized_steps: list[PlannedStep] = []
    for step in steps:
        params = dict(step.params)
        if step.tool_id == "marketing.web_research" and planned_search_terms:
            params["query"] = planned_search_terms[0]
            if len(planned_search_terms) > 1:
                params.setdefault(
                    "query_variants",
                    planned_search_terms[1 : 1 + max(1, research_plan.max_query_variants - 1)],
                )
            params.setdefault("max_query_variants", research_plan.max_query_variants)
            params.setdefault("results_per_query", research_plan.results_per_query)
            params.setdefault("fused_top_k", research_plan.fused_top_k)
            params.setdefault("min_unique_sources", research_plan.min_unique_sources)
            params.setdefault("search_budget", research_plan.web_search_budget)
            params.setdefault("research_depth_tier", research_plan.depth_tier)
        if step.tool_id in ("browser.playwright.inspect", "documents.highlight.extract"):
            params.setdefault("highlight_color", highlight_color)
        if step.tool_id == "documents.highlight.extract" and planned_keywords:
            params.setdefault("words", planned_keywords[:12])
        if step.tool_id == "documents.highlight.extract":
            params.setdefault("max_sources", research_plan.max_file_sources)
            params.setdefault("max_chunks", research_plan.max_file_chunks)
            params.setdefault("max_scan_pages", research_plan.max_file_scan_pages)
        if step.tool_id == "docs.create":
            params.setdefault("include_copied_highlights", True)
        normalized_steps.append(
            PlannedStep(tool_id=step.tool_id, title=step.title, params=params)
        )
    return normalized_steps


def enforce_web_only_research_path(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
    steps: list[PlannedStep],
    research_plan: ResearchBlueprint,
) -> list[PlannedStep]:
    if any(step.tool_id in GA_TOOL_IDS for step in steps):
        return steps

    web_only_raw = settings.get("__research_web_only")
    web_only_enabled = (
        bool(web_only_raw)
        if isinstance(web_only_raw, bool)
        else str(web_only_raw or "").strip().lower() in {"1", "true", "yes", "on"}
    )
    if not web_only_enabled:
        return steps

    constrained_steps = [
        step
        for step in steps
        if step.tool_id != "documents.highlight.extract"
    ]

    if not any(step.tool_id == "marketing.web_research" for step in constrained_steps):
        query = (
            research_plan.planned_search_terms[0]
            if research_plan.planned_search_terms
            else request.message
        )
        constrained_steps.insert(
            0,
            PlannedStep(
                tool_id="marketing.web_research",
                title="Search online sources",
                params={
                    "query": query,
                    "max_query_variants": research_plan.max_query_variants,
                    "results_per_query": research_plan.results_per_query,
                    "fused_top_k": research_plan.fused_top_k,
                    "min_unique_sources": research_plan.min_unique_sources,
                    "search_budget": research_plan.web_search_budget,
                    "research_depth_tier": research_plan.depth_tier,
                },
            ),
        )

    if not any(step.tool_id == "report.generate" for step in constrained_steps):
        constrained_steps.append(
            PlannedStep(
                tool_id="report.generate",
                title="Create concise executive output",
                params={"summary": request.message},
            )
        )
    return constrained_steps


def ensure_company_agent_highlight_step(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
    steps: list[PlannedStep],
    highlight_color: str,
    planned_keywords: list[str],
) -> list[PlannedStep]:
    if request.agent_mode != "company_agent":
        return steps
    if not _should_auto_insert_highlight_step(request=request, settings=settings):
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


def enforce_deep_file_scope_policy(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
    steps: list[PlannedStep],
) -> list[PlannedStep]:
    deep_search_mode = str(request.agent_mode or "").strip().lower() == "deep_search" or bool(
        settings.get("__deep_search_enabled")
    )
    if not deep_search_mode:
        return steps
    explicit_file_scope = bool(settings.get("__deep_search_prompt_scoped_pdfs")) or bool(
        settings.get("__deep_search_user_selected_files")
    ) or any(
        str(getattr(item, "file_id", "") or "").strip()
        for item in (request.attachments if isinstance(request.attachments, list) else [])
    )
    if explicit_file_scope:
        return steps
    return [step for step in steps if step.tool_id != "documents.highlight.extract"]
