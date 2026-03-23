from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.research_depth_profile import ResearchDepthProfile

from .text_helpers import truthy

_SCOPE_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


def bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(low, min(high, parsed))


def tokenize_scope(text: str) -> set[str]:
    def _canonical(raw: str) -> str:
        token = str(raw or "").strip().lower()
        for suffix in ("ization", "ation", "ments", "ment", "ities", "ity", "ing", "ed", "s"):
            if token.endswith(suffix) and (len(token) - len(suffix)) >= 4:
                token = token[: -len(suffix)]
                break
        return token

    return {
        _canonical(match.group(0))
        for match in _SCOPE_WORD_RE.finditer(str(text or ""))
        if len(match.group(0)) >= 4
    }


def rewrite_scope_drifted(*, message: str, agent_goal: str, rewritten_task: str) -> bool:
    source_tokens = tokenize_scope(" ".join([message, agent_goal]).strip())
    rewritten_tokens = tokenize_scope(rewritten_task)
    if not rewritten_tokens:
        return True
    if not source_tokens:
        return False
    novel_tokens = rewritten_tokens.difference(source_tokens)
    if not novel_tokens:
        return False
    novel_ratio = len(novel_tokens) / max(1, len(rewritten_tokens))
    novel_limit = max(4, int(len(source_tokens) * 0.75))
    return len(novel_tokens) > novel_limit or novel_ratio >= 0.45


def normalize_rewritten_task_scope(
    *,
    message: str,
    agent_goal: str,
    rewritten_task: str,
) -> str:
    cleaned_rewrite = " ".join(str(rewritten_task or "").split()).strip()
    if not cleaned_rewrite:
        return " ".join(str(message or "").split()).strip()
    if not rewrite_scope_drifted(message=message, agent_goal=agent_goal, rewritten_task=cleaned_rewrite):
        return cleaned_rewrite
    source_scope = " ".join([str(message or "").strip(), str(agent_goal or "").strip()]).strip()
    return source_scope[:900] if source_scope else cleaned_rewrite[:900]


def selected_file_ids(request: ChatRequest) -> list[str]:
    collected: list[str] = []
    for selection in request.index_selection.values():
        file_ids = getattr(selection, "file_ids", []) or []
        for file_id in file_ids:
            file_id_text = str(file_id).strip()
            if file_id_text:
                collected.append(file_id_text)
    return list(dict.fromkeys(collected))


def selected_index_id(request: ChatRequest) -> int | None:
    for raw_index_id in request.index_selection.keys():
        text = str(raw_index_id).strip()
        if text.isdigit():
            return int(text)
    return None


def retrieve_context_snippets(
    *,
    enabled: bool,
    query_parts: list[str],
    retriever: Callable[[str], list[str]],
) -> list[str]:
    if not enabled:
        return []
    query = " ".join([str(item).strip() for item in query_parts if str(item).strip()]).strip()
    if not query:
        return []
    try:
        return retriever(query) or []
    except Exception:
        return []


def workflow_stage_context_retrieval_enabled(
    *,
    settings: dict[str, Any],
    default: bool = False,
) -> bool:
    explicit_scope = settings.get("__allowed_tool_ids")
    if not isinstance(explicit_scope, list):
        return True
    return truthy(
        settings.get("agent.workflow_stage_context_retrieval_enabled"),
        default=default,
    )


def force_deep_search_profile(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
    depth_profile: ResearchDepthProfile,
) -> ResearchDepthProfile:
    deep_search_requested = str(request.agent_mode or "").strip().lower() == "deep_search" or truthy(
        settings.get("__deep_search_enabled"),
        default=False,
    )
    if not deep_search_requested:
        return depth_profile

    complexity = " ".join(str(settings.get("__deep_search_complexity") or "").split()).strip().lower()
    complex_mode = complexity == "complex"

    max_query_variants = bounded_int(
        settings.get("__research_max_query_variants"),
        default=max(18 if complex_mode else 12, depth_profile.max_query_variants),
        low=8,
        high=40,
    )
    results_per_query = bounded_int(
        settings.get("__research_results_per_query"),
        default=max(12 if complex_mode else 10, depth_profile.results_per_query),
        low=8,
        high=25,
    )
    source_budget_min = bounded_int(
        settings.get("__research_source_budget_min"),
        default=max(80 if complex_mode else 50, depth_profile.source_budget_min),
        low=20,
        high=200,
    )
    source_budget_max = bounded_int(
        settings.get("__research_source_budget_max"),
        default=max(180 if complex_mode else 100, depth_profile.source_budget_max),
        low=source_budget_min,
        high=220,
    )
    min_unique_sources = bounded_int(
        settings.get("__research_min_unique_sources"),
        default=max(source_budget_min, 50, depth_profile.min_unique_sources),
        low=source_budget_min,
        high=200,
    )
    file_source_budget_min = bounded_int(
        settings.get("__file_research_source_budget_min"),
        default=max(140 if complex_mode else 100, depth_profile.file_source_budget_min),
        low=24,
        high=220,
    )
    file_source_budget_max = bounded_int(
        settings.get("__file_research_source_budget_max"),
        default=max(220 if complex_mode else 180, depth_profile.file_source_budget_max),
        low=file_source_budget_min,
        high=240,
    )
    max_file_sources = bounded_int(
        settings.get("__file_research_max_sources"),
        default=max(file_source_budget_min, depth_profile.max_file_sources),
        low=file_source_budget_min,
        high=240,
    )
    max_file_chunks = bounded_int(
        settings.get("__file_research_max_chunks"),
        default=max(1800 if complex_mode else 1400, depth_profile.max_file_chunks),
        low=200,
        high=3000,
    )
    max_file_scan_pages = bounded_int(
        settings.get("__file_research_max_scan_pages"),
        default=max(220 if complex_mode else 180, depth_profile.max_file_scan_pages),
        low=20,
        high=300,
    )

    return replace(
        depth_profile,
        tier="deep_research",
        rationale=(
            "Deep Search mode requested; using complex high-coverage profile."
            if complex_mode
            else "Deep Search mode requested; using broad standard deep-research profile."
        ),
        max_query_variants=max_query_variants,
        results_per_query=results_per_query,
        fused_top_k=max(source_budget_max, depth_profile.fused_top_k),
        max_live_inspections=max(18, depth_profile.max_live_inspections),
        min_unique_sources=min_unique_sources,
        source_budget_min=source_budget_min,
        source_budget_max=source_budget_max,
        min_keywords=max(16, depth_profile.min_keywords),
        file_source_budget_min=file_source_budget_min,
        file_source_budget_max=file_source_budget_max,
        max_file_sources=max_file_sources,
        max_file_chunks=max_file_chunks,
        max_file_scan_pages=max_file_scan_pages,
        include_execution_why=True,
    )


def scoped_agent_goal_for_execution(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
) -> str:
    requested_mode = " ".join(str(request.agent_mode or "").split()).strip().lower()
    if requested_mode != "company_agent":
        return ""
    if truthy(settings.get("__research_web_only"), default=False):
        return ""
    return " ".join(str(request.agent_goal or "").split()).strip()


def extract_contract_fields(task_contract: dict[str, Any]) -> dict[str, Any]:
    contract_objective = " ".join(str(task_contract.get("objective") or "").split()).strip()
    contract_outputs = [
        str(item).strip()
        for item in (
            task_contract.get("required_outputs")
            if isinstance(task_contract.get("required_outputs"), list)
            else []
        )
        if str(item).strip()
    ][:6]
    contract_facts = [
        str(item).strip()
        for item in (
            task_contract.get("required_facts")
            if isinstance(task_contract.get("required_facts"), list)
            else []
        )
        if str(item).strip()
    ][:6]
    contract_actions = [
        str(item).strip()
        for item in (
            task_contract.get("required_actions")
            if isinstance(task_contract.get("required_actions"), list)
            else []
        )
        if str(item).strip()
    ][:6]
    contract_missing_requirements = [
        str(item).strip()
        for item in (
            task_contract.get("missing_requirements")
            if isinstance(task_contract.get("missing_requirements"), list)
            else []
        )
        if str(item).strip()
    ][:6]
    contract_success_checks = [
        str(item).strip()
        for item in (
            task_contract.get("success_checks")
            if isinstance(task_contract.get("success_checks"), list)
            else []
        )
        if str(item).strip()
    ][:8]
    contract_target = " ".join(str(task_contract.get("delivery_target") or "").split()).strip()
    return {
        "contract_objective": contract_objective,
        "contract_outputs": contract_outputs,
        "contract_facts": contract_facts,
        "contract_actions": contract_actions,
        "contract_missing_requirements": contract_missing_requirements,
        "contract_success_checks": contract_success_checks,
        "contract_target": contract_target,
    }


def clarification_gate_state(
    *,
    settings: dict[str, Any],
    request: ChatRequest,
    contract_blocking_requirements: list[str],
) -> tuple[bool, bool, bool]:
    clarification_gate_enabled = truthy(
        settings.get("agent.clarification_gate_enabled"),
        default=True,
    )
    defer_clarification_until_exploration = truthy(
        settings.get("agent.defer_clarification_until_exploration"),
        default=True,
    )
    deep_research_requested = bool(
        str(request.agent_mode or "").strip().lower() == "deep_search"
        or truthy(settings.get("__deep_search_enabled"), default=False)
        or str(settings.get("__research_depth_tier") or "").strip().lower()
        in {"deep_research", "deep_analytics"}
    )
    clarification_blocked = clarification_gate_enabled and bool(contract_blocking_requirements)
    clarification_deferred = False
    if clarification_blocked and deep_research_requested:
        clarification_blocked = False
        clarification_deferred = True
    if clarification_blocked and defer_clarification_until_exploration:
        clarification_blocked = False
        clarification_deferred = True
    return clarification_blocked, clarification_deferred, deep_research_requested
