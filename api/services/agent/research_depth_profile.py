from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

_log = logging.getLogger(__name__)

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value
from api.services.agent.planner_helpers import infer_intent_signals_from_text

DEPTH_TIERS = ("quick", "standard", "deep_research", "deep_analytics", "expert")


@dataclass(slots=True, frozen=True)
class ResearchDepthProfile:
    tier: str
    rationale: str
    max_query_variants: int
    results_per_query: int
    fused_top_k: int
    max_live_inspections: int
    min_unique_sources: int
    source_budget_min: int
    source_budget_max: int
    min_keywords: int
    file_source_budget_min: int
    file_source_budget_max: int
    max_file_sources: int
    max_file_chunks: int
    max_file_scan_pages: int
    simple_explanation_required: bool
    include_execution_why: bool
    # Number of iterative search rounds (quick=1, standard=2, deep=3, expert=4).
    # Round 1: broad coverage; round 2+: gap-fill queries on under-covered topics.
    max_search_rounds: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "rationale": self.rationale,
            "max_query_variants": self.max_query_variants,
            "results_per_query": self.results_per_query,
            "fused_top_k": self.fused_top_k,
            "max_live_inspections": self.max_live_inspections,
            "min_unique_sources": self.min_unique_sources,
            "source_budget_min": self.source_budget_min,
            "source_budget_max": self.source_budget_max,
            "min_keywords": self.min_keywords,
            "file_source_budget_min": self.file_source_budget_min,
            "file_source_budget_max": self.file_source_budget_max,
            "max_file_sources": self.max_file_sources,
            "max_file_chunks": self.max_file_chunks,
            "max_file_scan_pages": self.max_file_scan_pages,
            "simple_explanation_required": self.simple_explanation_required,
            "include_execution_why": self.include_execution_why,
            "max_search_rounds": self.max_search_rounds,
        }


def _clamp(value: int, *, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return None


def _coerce_optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _profile_for_tier(tier: str) -> dict[str, int]:
    if tier == "quick":
        return {
            "max_query_variants": 3,
            "results_per_query": 6,
            "fused_top_k": 20,
            "max_live_inspections": 4,
            "min_unique_sources": 5,
            "source_budget_min": 5,
            "source_budget_max": 15,
            "min_keywords": 6,
            "file_source_budget_min": 5,
            "file_source_budget_max": 15,
            "max_file_sources": 15,
            "max_file_chunks": 120,
            "max_file_scan_pages": 15,
            "max_search_rounds": 1,
        }
    if tier == "deep_research":
        return {
            "max_query_variants": 20,
            "results_per_query": 15,
            "fused_top_k": 250,
            "max_live_inspections": 50,
            "min_unique_sources": 80,
            "source_budget_min": 100,
            "source_budget_max": 200,
            "min_keywords": 24,
            "file_source_budget_min": 150,
            "file_source_budget_max": 300,
            "max_file_sources": 300,
            "max_file_chunks": 2000,
            "max_file_scan_pages": 200,
            "max_search_rounds": 3,
        }
    if tier == "deep_analytics":
        return {
            "max_query_variants": 12,
            "results_per_query": 12,
            "fused_top_k": 100,
            "max_live_inspections": 24,
            "min_unique_sources": 35,
            "source_budget_min": 35,
            "source_budget_max": 90,
            "min_keywords": 18,
            "file_source_budget_min": 60,
            "file_source_budget_max": 180,
            "max_file_sources": 180,
            "max_file_chunks": 1200,
            "max_file_scan_pages": 140,
            "max_search_rounds": 2,
        }
    if tier == "expert":
        return {
            "max_query_variants": 35,
            "results_per_query": 25,
            "fused_top_k": 500,
            "max_live_inspections": 100,
            "min_unique_sources": 150,
            "source_budget_min": 200,
            "source_budget_max": 500,
            "min_keywords": 40,
            "file_source_budget_min": 300,
            "file_source_budget_max": 600,
            "max_file_sources": 600,
            "max_file_chunks": 5000,
            "max_file_scan_pages": 500,
            "max_search_rounds": 4,
        }
    # standard (default)
    return {
        "max_query_variants": 5,
        "results_per_query": 8,
        "fused_top_k": 36,
        "max_live_inspections": 8,
        "min_unique_sources": 8,
        "source_budget_min": 8,
        "source_budget_max": 24,
        "min_keywords": 10,
        "file_source_budget_min": 12,
        "file_source_budget_max": 40,
        "max_file_sources": 40,
        "max_file_chunks": 320,
        "max_file_scan_pages": 40,
        "max_search_rounds": 1,
    }


def _default_rationale(tier: str) -> str:
    if tier == "quick":
        return "Fast coverage profile selected for a concise request."
    if tier == "deep_research":
        return "Deep research profile selected for broad evidence collection."
    if tier == "deep_analytics":
        return "Deep analytics profile selected for data-heavy analysis."
    if tier == "expert":
        return "Expert profile selected for maximum source coverage and credibility verification."
    return "Balanced coverage profile selected."


def _classify_depth_with_llm(
    *,
    message: str,
    agent_goal: str | None = None,
    user_preferences: dict[str, Any] | None = None,
    agent_mode: str = "",
) -> dict[str, Any]:
    if not env_bool("MAIA_AGENT_LLM_RESEARCH_DEPTH_PROFILE_ENABLED", default=True):
        return {}

    payload = {
        "message": str(message or "").strip(),
        "agent_goal": str(agent_goal or "").strip(),
        "user_preferences": sanitize_json_value(user_preferences or {}),
        "agent_mode": str(agent_mode or "").strip(),
        "available_tiers": list(DEPTH_TIERS),
    }
    response = call_json_response(
        system_prompt=(
            "You classify enterprise agent research depth. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only with this schema:\n"
            "{\n"
            '  "tier": "quick|standard|deep_research|deep_analytics|expert",\n'
            '  "rationale": "short reason",\n'
            '  "source_budget_min": 15,\n'
            '  "source_budget_max": 50,\n'
            '  "max_query_variants": 8,\n'
            '  "results_per_query": 12,\n'
            '  "fused_top_k": 60,\n'
            '  "max_live_inspections": 12,\n'
            '  "min_unique_sources": 15,\n'
            '  "min_keywords": 14,\n'
            '  "file_source_budget_min": 20,\n'
            '  "file_source_budget_max": 70,\n'
            '  "max_file_sources": 70,\n'
            '  "max_file_chunks": 500,\n'
            '  "max_file_scan_pages": 60,\n'
            '  "max_search_rounds": 2,\n'
            '  "simple_explanation_required": false,\n'
            '  "include_execution_why": false\n'
            "}\n"
            "Rules:\n"
            "- Infer depth from user intent and requested rigor.\n"
            "- For a general overview request that will be delivered as an email or short report, choose `standard` even if the user asks for authoritative sources.\n"
            "- Do not upgrade to deep_research just because the topic is broad or because authoritative sources are requested.\n"
            "- Use deep_research only when the user explicitly wants exhaustive breadth, benchmark-heavy coverage, literature/paper review, peer-reviewed depth, latest developments, market/regulatory segmentation, or similarly high-rigor multi-angle work.\n"
            "- deep_research: 100-200 sources, 20 query variants, 3 rounds.\n"
            "- expert: 200-500 sources, 35 query variants, 4 rounds.\n"
            "- Keep source budgets realistic and internally consistent.\n"
            "- If unsure, choose `standard`.\n\n"
            f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
        ),
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=420,
    )
    normalized = sanitize_json_value(response) if isinstance(response, dict) else {}
    return normalized if isinstance(normalized, dict) else {}


def _should_cap_to_standard(
    *,
    message: str,
    agent_goal: str | None,
    agent_mode: str,
    requested_tier: str,
) -> bool:
    if requested_tier not in {"deep_research", "deep_analytics", "expert"}:
        return False
    if str(agent_mode or "").strip().lower() == "deep_search":
        return False

    text = " ".join(f"{message or ''} {agent_goal or ''}".split()).strip().lower()
    signals = infer_intent_signals_from_text(message=message, agent_goal=agent_goal or "")
    wants_delivery = bool(signals.get("wants_send")) or bool(signals.get("wants_report"))
    explicit_deep_markers = (
        "deep research",
        "exhaustive",
        "comprehensive analysis",
        "systematic review",
        "literature review",
        "peer-reviewed",
        "peer reviewed",
        "recent papers",
        "latest papers",
        "benchmark",
        "benchmarks",
        "compare",
        "comparison",
        "versus",
        "vs ",
        "regulation",
        "regulatory",
        "policy",
        "market size",
        "forecast",
        "academic",
        "arxiv",
        "survey paper",
    )
    if not wants_delivery:
        return False
    return not any(marker in text for marker in explicit_deep_markers)


def derive_research_depth_profile(
    *,
    message: str,
    agent_goal: str | None = None,
    user_preferences: dict[str, Any] | None = None,
    agent_mode: str = "",
) -> ResearchDepthProfile:
    llm_profile = _classify_depth_with_llm(
        message=message,
        agent_goal=agent_goal,
        user_preferences=user_preferences,
        agent_mode=agent_mode,
    )

    requested_tier = str(llm_profile.get("tier") or "").strip().lower()
    if requested_tier and requested_tier not in DEPTH_TIERS:
        _log.warning(
            "derive_research_depth_profile: LLM returned unknown tier %r; falling back to 'standard'",
            requested_tier,
        )
    elif not requested_tier:
        _log.warning(
            "derive_research_depth_profile: LLM returned no tier (profile=%r); falling back to 'standard'",
            dict(llm_profile) if llm_profile else {},
        )
    tier = requested_tier if requested_tier in DEPTH_TIERS else "standard"
    normalized_agent_mode = str(agent_mode or "").strip().lower()
    if normalized_agent_mode == "deep_search":
        tier = "deep_research"
    if normalized_agent_mode == "company_agent" and tier == "quick":
        tier = "standard"
    if _should_cap_to_standard(
        message=message,
        agent_goal=agent_goal,
        agent_mode=agent_mode,
        requested_tier=tier,
    ):
        tier = "standard"

    base = _profile_for_tier(tier)
    allow_llm_budget_override = tier in {"deep_research", "deep_analytics", "expert"}
    source_budget_min_raw = _coerce_optional_int(llm_profile.get("source_budget_min"))
    source_budget_max_raw = _coerce_optional_int(llm_profile.get("source_budget_max"))

    source_budget_min = int(base["source_budget_min"])
    source_budget_max = int(base["source_budget_max"])
    if allow_llm_budget_override and (source_budget_min_raw is not None or source_budget_max_raw is not None):
        candidate_min = source_budget_min_raw if source_budget_min_raw is not None else source_budget_min
        candidate_max = source_budget_max_raw if source_budget_max_raw is not None else source_budget_max
        low = _clamp(candidate_min, low=3, high=500)
        high = _clamp(candidate_max, low=3, high=600)
        if high < low:
            low, high = high, low
        source_budget_min = low
        source_budget_max = high

    max_query_variants_seed = (
        _coerce_optional_int(llm_profile.get("max_query_variants"))
        if allow_llm_budget_override
        else None
    )
    max_query_variants = _clamp(
        max_query_variants_seed or int(base["max_query_variants"]),
        low=2,
        high=40,
    )
    results_per_query_seed = (
        _coerce_optional_int(llm_profile.get("results_per_query"))
        if allow_llm_budget_override
        else None
    )
    results_per_query = _clamp(
        results_per_query_seed or int(base["results_per_query"]),
        low=4,
        high=30,
    )
    fused_top_k_seed = (
        _coerce_optional_int(llm_profile.get("fused_top_k"))
        if allow_llm_budget_override
        else None
    )
    fused_top_k = _clamp(
        fused_top_k_seed or int(base["fused_top_k"]),
        low=8,
        high=600,
    )
    max_live_inspections_seed = (
        _coerce_optional_int(llm_profile.get("max_live_inspections"))
        if allow_llm_budget_override
        else None
    )
    max_live_inspections = _clamp(
        max_live_inspections_seed or int(base["max_live_inspections"]),
        low=2,
        high=120,
    )
    min_unique_sources_seed = (
        _coerce_optional_int(llm_profile.get("min_unique_sources"))
        if allow_llm_budget_override
        else None
    )
    min_unique_sources = _clamp(
        min_unique_sources_seed or int(base["min_unique_sources"]),
        low=3,
        high=500,
    )
    min_keywords_seed = (
        _coerce_optional_int(llm_profile.get("min_keywords"))
        if allow_llm_budget_override
        else None
    )
    min_keywords = _clamp(
        min_keywords_seed or int(base["min_keywords"]),
        low=4,
        high=50,
    )
    file_source_budget_min_seed = (
        _coerce_optional_int(llm_profile.get("file_source_budget_min"))
        if allow_llm_budget_override
        else None
    )
    file_source_budget_min = _clamp(
        file_source_budget_min_seed or int(base["file_source_budget_min"]),
        low=3,
        high=600,
    )
    file_source_budget_max_seed = (
        _coerce_optional_int(llm_profile.get("file_source_budget_max"))
        if allow_llm_budget_override
        else None
    )
    file_source_budget_max = _clamp(
        file_source_budget_max_seed or int(base["file_source_budget_max"]),
        low=3,
        high=700,
    )
    if file_source_budget_max < file_source_budget_min:
        file_source_budget_min, file_source_budget_max = file_source_budget_max, file_source_budget_min
    max_file_sources_seed = (
        _coerce_optional_int(llm_profile.get("max_file_sources"))
        if allow_llm_budget_override
        else None
    )
    max_file_sources = _clamp(
        max_file_sources_seed or int(base["max_file_sources"]),
        low=3,
        high=700,
    )
    max_file_chunks_seed = (
        _coerce_optional_int(llm_profile.get("max_file_chunks"))
        if allow_llm_budget_override
        else None
    )
    max_file_chunks = _clamp(
        max_file_chunks_seed or int(base["max_file_chunks"]),
        low=40,
        high=6000,
    )
    max_file_scan_pages_seed = (
        _coerce_optional_int(llm_profile.get("max_file_scan_pages"))
        if allow_llm_budget_override
        else None
    )
    max_file_scan_pages = _clamp(
        max_file_scan_pages_seed or int(base["max_file_scan_pages"]),
        low=8,
        high=600,
    )
    max_search_rounds_seed = (
        _coerce_optional_int(llm_profile.get("max_search_rounds"))
        if allow_llm_budget_override
        else None
    )
    max_search_rounds = _clamp(
        max_search_rounds_seed or int(base.get("max_search_rounds", 1)),
        low=1,
        high=4,
    )

    fused_top_k = max(fused_top_k, source_budget_max)
    min_unique_sources = max(min_unique_sources, source_budget_min)
    max_file_sources = max(max_file_sources, file_source_budget_min)

    prefs = user_preferences if isinstance(user_preferences, dict) else {}
    simple_pref = _coerce_bool(prefs.get("simple_explanation_required"))
    explain_pref = _coerce_bool(prefs.get("include_execution_why"))
    simple_from_llm = _coerce_bool(llm_profile.get("simple_explanation_required"))
    explain_from_llm = _coerce_bool(llm_profile.get("include_execution_why"))

    rationale = " ".join(str(llm_profile.get("rationale") or "").split()).strip()[:240]
    if not rationale:
        rationale = _default_rationale(tier)

    return ResearchDepthProfile(
        tier=tier,
        rationale=rationale,
        max_query_variants=max_query_variants,
        results_per_query=results_per_query,
        fused_top_k=fused_top_k,
        max_live_inspections=max_live_inspections,
        min_unique_sources=min_unique_sources,
        source_budget_min=_clamp(source_budget_min, low=3, high=500),
        source_budget_max=_clamp(source_budget_max, low=source_budget_min, high=600),
        min_keywords=min_keywords,
        file_source_budget_min=file_source_budget_min,
        file_source_budget_max=file_source_budget_max,
        max_file_sources=max_file_sources,
        max_file_chunks=max_file_chunks,
        max_file_scan_pages=max_file_scan_pages,
        simple_explanation_required=(
            simple_from_llm if simple_from_llm is not None else bool(simple_pref)
        ),
        include_execution_why=(
            explain_from_llm if explain_from_llm is not None else bool(explain_pref)
        ),
        max_search_rounds=max_search_rounds,
    )


__all__ = ["ResearchDepthProfile", "derive_research_depth_profile", "DEPTH_TIERS"]
