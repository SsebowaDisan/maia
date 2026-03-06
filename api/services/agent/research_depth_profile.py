from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

DEPTH_TIERS = ("quick", "standard", "deep_research", "deep_analytics")


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
            "max_query_variants": 2,
            "results_per_query": 4,
            "fused_top_k": 8,
            "max_live_inspections": 2,
            "min_unique_sources": 3,
            "source_budget_min": 3,
            "source_budget_max": 8,
            "min_keywords": 4,
            "file_source_budget_min": 3,
            "file_source_budget_max": 8,
            "max_file_sources": 8,
            "max_file_chunks": 80,
            "max_file_scan_pages": 10,
        }
    if tier == "deep_research":
        return {
            "max_query_variants": 12,
            "results_per_query": 10,
            "fused_top_k": 120,
            "max_live_inspections": 24,
            "min_unique_sources": 50,
            "source_budget_min": 60,
            "source_budget_max": 100,
            "min_keywords": 18,
            "file_source_budget_min": 100,
            "file_source_budget_max": 200,
            "max_file_sources": 200,
            "max_file_chunks": 1200,
            "max_file_scan_pages": 140,
        }
    if tier == "deep_analytics":
        return {
            "max_query_variants": 8,
            "results_per_query": 10,
            "fused_top_k": 60,
            "max_live_inspections": 14,
            "min_unique_sources": 20,
            "source_budget_min": 20,
            "source_budget_max": 60,
            "min_keywords": 14,
            "file_source_budget_min": 40,
            "file_source_budget_max": 120,
            "max_file_sources": 120,
            "max_file_chunks": 700,
            "max_file_scan_pages": 90,
        }
    return {
        "max_query_variants": 4,
        "results_per_query": 8,
        "fused_top_k": 24,
        "max_live_inspections": 4,
        "min_unique_sources": 8,
        "source_budget_min": 8,
        "source_budget_max": 24,
        "min_keywords": 10,
        "file_source_budget_min": 12,
        "file_source_budget_max": 40,
        "max_file_sources": 40,
        "max_file_chunks": 260,
        "max_file_scan_pages": 40,
    }


def _default_rationale(tier: str) -> str:
    if tier == "quick":
        return "Fast coverage profile selected for a concise request."
    if tier == "deep_research":
        return "Deep research profile selected for broad evidence collection."
    if tier == "deep_analytics":
        return "Deep analytics profile selected for data-heavy analysis."
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
            '  "tier": "quick|standard|deep_research|deep_analytics",\n'
            '  "rationale": "short reason",\n'
            '  "source_budget_min": 8,\n'
            '  "source_budget_max": 24,\n'
            '  "max_query_variants": 4,\n'
            '  "results_per_query": 8,\n'
            '  "fused_top_k": 24,\n'
            '  "max_live_inspections": 4,\n'
            '  "min_unique_sources": 8,\n'
            '  "min_keywords": 10,\n'
            '  "file_source_budget_min": 12,\n'
            '  "file_source_budget_max": 40,\n'
            '  "max_file_sources": 40,\n'
            '  "max_file_chunks": 260,\n'
            '  "max_file_scan_pages": 40,\n'
            '  "simple_explanation_required": false,\n'
            '  "include_execution_why": false\n'
            "}\n"
            "Rules:\n"
            "- Infer depth from user intent and requested rigor.\n"
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
    tier = requested_tier if requested_tier in DEPTH_TIERS else "standard"
    normalized_agent_mode = str(agent_mode or "").strip().lower()
    if normalized_agent_mode == "deep_search":
        tier = "deep_research"
    if normalized_agent_mode == "company_agent" and tier == "quick":
        tier = "standard"

    base = _profile_for_tier(tier)
    source_budget_min_raw = _coerce_optional_int(llm_profile.get("source_budget_min"))
    source_budget_max_raw = _coerce_optional_int(llm_profile.get("source_budget_max"))

    source_budget_min = int(base["source_budget_min"])
    source_budget_max = int(base["source_budget_max"])
    if source_budget_min_raw is not None or source_budget_max_raw is not None:
        candidate_min = source_budget_min_raw if source_budget_min_raw is not None else source_budget_min
        candidate_max = source_budget_max_raw if source_budget_max_raw is not None else source_budget_max
        low = _clamp(candidate_min, low=3, high=200)
        high = _clamp(candidate_max, low=3, high=220)
        if high < low:
            low, high = high, low
        source_budget_min = low
        source_budget_max = high

    max_query_variants = _clamp(
        _coerce_optional_int(llm_profile.get("max_query_variants")) or int(base["max_query_variants"]),
        low=2,
        high=20,
    )
    results_per_query = _clamp(
        _coerce_optional_int(llm_profile.get("results_per_query")) or int(base["results_per_query"]),
        low=4,
        high=25,
    )
    fused_top_k = _clamp(
        _coerce_optional_int(llm_profile.get("fused_top_k")) or int(base["fused_top_k"]),
        low=8,
        high=220,
    )
    max_live_inspections = _clamp(
        _coerce_optional_int(llm_profile.get("max_live_inspections"))
        or int(base["max_live_inspections"]),
        low=2,
        high=40,
    )
    min_unique_sources = _clamp(
        _coerce_optional_int(llm_profile.get("min_unique_sources")) or int(base["min_unique_sources"]),
        low=3,
        high=200,
    )
    min_keywords = _clamp(
        _coerce_optional_int(llm_profile.get("min_keywords")) or int(base["min_keywords"]),
        low=4,
        high=40,
    )
    file_source_budget_min = _clamp(
        _coerce_optional_int(llm_profile.get("file_source_budget_min"))
        or int(base["file_source_budget_min"]),
        low=3,
        high=220,
    )
    file_source_budget_max = _clamp(
        _coerce_optional_int(llm_profile.get("file_source_budget_max"))
        or int(base["file_source_budget_max"]),
        low=3,
        high=240,
    )
    if file_source_budget_max < file_source_budget_min:
        file_source_budget_min, file_source_budget_max = file_source_budget_max, file_source_budget_min
    max_file_sources = _clamp(
        _coerce_optional_int(llm_profile.get("max_file_sources")) or int(base["max_file_sources"]),
        low=3,
        high=240,
    )
    max_file_chunks = _clamp(
        _coerce_optional_int(llm_profile.get("max_file_chunks")) or int(base["max_file_chunks"]),
        low=40,
        high=3000,
    )
    max_file_scan_pages = _clamp(
        _coerce_optional_int(llm_profile.get("max_file_scan_pages")) or int(base["max_file_scan_pages"]),
        low=8,
        high=300,
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
        source_budget_min=_clamp(source_budget_min, low=3, high=200),
        source_budget_max=_clamp(source_budget_max, low=source_budget_min, high=220),
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
    )


__all__ = ["ResearchDepthProfile", "derive_research_depth_profile", "DEPTH_TIERS"]
