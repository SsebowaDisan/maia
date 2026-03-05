from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.llm_research_blueprint import build_research_blueprint
from api.services.agent.planner import PlannedStep, is_deep_research_request

RESEARCH_INTENT_HINTS = (
    "research",
    "analyze",
    "analysis",
    "compare",
    "competitor",
    "market",
    "source",
    "citations",
    "benchmark",
    "latest",
    "news",
)
HIGHLIGHT_HINTS = (
    "highlight",
    "copied words",
    "copied word",
    "extract keywords",
    "keyword extraction",
)
FILE_HINTS = ("file", "files", "pdf", "document", "page")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")


@dataclass(slots=True, frozen=True)
class ResearchBlueprint:
    deep_research_mode: bool
    highlight_color: str
    planned_search_terms: list[str]
    planned_keywords: list[str]


def _keyword_floor_for_request(request: ChatRequest) -> int:
    text = " ".join([str(request.message or "").strip(), str(request.agent_goal or "").strip()]).strip()
    lowered = text.lower()
    token_count = len(WORD_RE.findall(text))
    has_research_signal = any(token in lowered for token in RESEARCH_INTENT_HINTS)
    if token_count <= 7 and not has_research_signal:
        return 4
    if token_count <= 12 and not has_research_signal:
        return 6
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


def _should_auto_insert_highlight_step(request: ChatRequest) -> bool:
    combined = " ".join([str(request.message or "").strip(), str(request.agent_goal or "").strip()]).lower()
    if not combined:
        return False
    if any(hint in combined for hint in HIGHLIGHT_HINTS):
        return True
    if _has_selected_files(request) and any(hint in combined for hint in FILE_HINTS):
        return True
    return False


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
        min_keywords=_keyword_floor_for_request(request),
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
    if not _should_auto_insert_highlight_step(request):
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
