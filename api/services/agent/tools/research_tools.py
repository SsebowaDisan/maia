from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote_plus, urlparse

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.research_helpers import (
    classify_provider_failure as _classify_provider_failure,
    extract_search_variants as _extract_search_variants,
    fuse_search_results as _fuse_search_results,
    normalize_search_provider as _normalize_search_provider,
    safe_snippet as _safe_snippet,
    truthy as _truthy,
)
from api.services.agent.tools.theater_cursor import with_scene

SITE_TOKEN_RE = re.compile(r"\bsite:([A-Za-z0-9.-]+)", re.IGNORECASE)


def _as_bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(low, min(high, parsed))


def _search_results_url(provider: str, query: str) -> str:
    normalized = " ".join(str(query or "").split()).strip()
    if not normalized:
        return ""
    if provider == "brave_search":
        return f"https://search.brave.com/search?q={quote_plus(normalized)}"
    if provider == "bing_search":
        return f"https://www.bing.com/search?q={quote_plus(normalized)}"
    return ""


def _hostname_label(url: str) -> str:
    try:
        host = str(urlparse(url).netloc or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _normalize_host(value: str) -> str:
    raw = " ".join(str(value or "").split()).strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = str(parsed.hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _url_matches_domain_scope(url: str, hosts: list[str]) -> bool:
    if not hosts:
        return True
    candidate_host = _normalize_host(url)
    if not candidate_host:
        return False
    for allowed in hosts:
        if not allowed:
            continue
        if candidate_host == allowed or candidate_host.endswith(f".{allowed}"):
            return True
    return False


def _clean_domain_scope_hosts(raw: Any) -> list[str]:
    if isinstance(raw, str):
        rows = [raw]
    elif isinstance(raw, list):
        rows = [str(item or "") for item in raw]
    else:
        rows = []
    hosts: list[str] = []
    for row in rows:
        normalized = _normalize_host(row)
        if not normalized or normalized in hosts:
            continue
        hosts.append(normalized)
        if len(hosts) >= 6:
            break
    return hosts


def _resolve_domain_scope_hosts(
    *,
    params: dict[str, Any],
    context_settings: dict[str, Any],
    query: str,
    query_variants: list[str],
) -> list[str]:
    explicit_scope = _clean_domain_scope_hosts(params.get("domain_scope"))
    if explicit_scope:
        return explicit_scope

    target_url = str(params.get("target_url") or context_settings.get("__task_target_url") or "").strip()
    target_host = _normalize_host(target_url)
    if target_host:
        return [target_host]

    derived: list[str] = []
    for text in [query, *query_variants[:6]]:
        for match in SITE_TOKEN_RE.findall(str(text or "")):
            host = _normalize_host(match)
            if not host or host in derived:
                continue
            derived.append(host)
            if len(derived) >= 4:
                break
        if len(derived) >= 4:
            break
    return derived


def _resolve_domain_scope_mode(*, params: dict[str, Any], domain_scope_hosts: list[str]) -> str:
    raw_mode = " ".join(str(params.get("domain_scope_mode") or "").split()).strip().lower()
    if raw_mode in {"strict", "prefer", "off"}:
        return raw_mode
    if domain_scope_hosts and _truthy(params.get("enforce_domain_scope"), default=False):
        return "strict"
    return "off"


def _apply_domain_scope(
    *,
    rows: list[dict[str, Any]],
    domain_scope_hosts: list[str],
    domain_scope_mode: str,
) -> tuple[list[dict[str, Any]], int]:
    if domain_scope_mode == "off" or not domain_scope_hosts:
        return rows, 0
    filtered = [
        row
        for row in rows
        if isinstance(row, dict)
        and _url_matches_domain_scope(str(row.get("url") or ""), domain_scope_hosts)
    ]
    if filtered:
        return filtered, max(0, len(rows) - len(filtered))
    if domain_scope_mode == "prefer":
        return rows, 0
    return [], len(rows)


def _website_scene_payload(
    *,
    lane: str,
    primary_index: int,
    secondary_index: int = 1,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return with_scene(
        payload or {},
        scene_surface="website",
        lane=lane,
        primary_index=primary_index,
        secondary_index=secondary_index,
    )


_BRANCH_LABELS = (
    "Factual",
    "Financial & Economic",
    "Competitive Landscape",
    "Academic Research",
    "News & Current Events",
    "Expert Opinion",
    "Historical Context",
    "Market & Industry",
    "People & Society",
    "Policy & Governance",
    "Technology & Innovation",
    "Risk & Security",
    "Environment & Sustainability",
    "Legal & Regulatory",
    "Products & Services",
    "Leadership & Strategy",
    "Scientific Evidence",
    "Case Studies",
)

_BRANCH_PROVIDER_MAP: dict[str, list[str]] = {
    "Factual":                  ["brave_search", "bing_search"],
    "Financial & Economic":     ["sec_edgar", "brave_search"],
    "Competitive Landscape":    ["brave_search", "bing_search"],
    "Academic Research":        ["arxiv", "brave_search"],
    "News & Current Events":    ["newsapi", "brave_search"],
    "Expert Opinion":           ["arxiv", "brave_search"],
    "Historical Context":       ["brave_search", "bing_search"],
    "Market & Industry":        ["brave_search", "newsapi"],
    "People & Society":         ["brave_search", "bing_search"],
    "Policy & Governance":      ["brave_search", "newsapi"],
    "Technology & Innovation":  ["arxiv", "brave_search"],
    "Risk & Security":          ["newsapi", "brave_search"],
    "Environment & Sustainability": ["arxiv", "brave_search"],
    "Legal & Regulatory":       ["brave_search", "bing_search"],
    "Products & Services":      ["brave_search", "bing_search"],
    "Leadership & Strategy":    ["brave_search", "newsapi"],
    "Scientific Evidence":      ["arxiv", "brave_search"],
    "Case Studies":             ["brave_search", "bing_search"],
}

# ── Universal branch signal sets ─────────────────────────────────────────────
# Each frozenset drives inclusion of an optional branch for any question type.
_SIG_FINANCIAL = frozenset([
    "revenue", "profit", "earnings", "stock", "ipo", "merger", "acquisition",
    "annual report", "10-k", "balance sheet", "cash flow", "financial",
    "gdp", "inflation", "fiscal", "budget", "economy", "economic", "investment",
    "funding", "valuation", "market cap", "dividend", "interest rate",
])
_SIG_ACADEMIC = frozenset([
    "research", "study", "paper", "algorithm", "model", "science", "survey",
    "machine learning", "neural", "academic", "theory", "clinical", "evidence",
    "experiment", "methodology", "findings", "hypothesis", "peer-reviewed",
])
_SIG_PEOPLE_SOCIETY = frozenset([
    "population", "demographics", "health", "education", "poverty", "society",
    "community", "welfare", "social", "human rights", "gender", "inequality",
    "public health", "mortality", "life expectancy", "labour", "workforce",
])
_SIG_POLICY_GOVERNANCE = frozenset([
    "government", "policy", "politics", "election", "regulation", "law",
    "governance", "compliance", "legislation", "parliament", "congress",
    "administration", "ministry", "constitution", "treaty", "sanction",
])
_SIG_TECHNOLOGY = frozenset([
    "technology", "software", "hardware", "ai", "artificial intelligence",
    "digital", "internet", "cloud", "data", "cybersecurity", "blockchain",
    "innovation", "startup", "engineering", "computing", "automation",
    "robotics", "semiconductor", "platform", "api", "framework",
])
_SIG_RISK_SECURITY = frozenset([
    "risk", "threat", "security", "conflict", "war", "attack", "vulnerability",
    "danger", "crisis", "instability", "terrorism", "fraud", "breach",
    "disaster", "failure", "liability", "exposure", "incident",
])
_SIG_ENVIRONMENT = frozenset([
    "climate", "environment", "sustainability", "carbon", "emissions",
    "biodiversity", "pollution", "renewable", "energy", "ecosystem",
    "deforestation", "weather", "temperature", "sea level", "drought",
])
_SIG_LEGAL = frozenset([
    "legal", "law", "court", "lawsuit", "litigation", "regulation",
    "compliance", "contract", "ip", "patent", "copyright", "antitrust",
    "regulatory", "enforcement", "jurisdiction", "statute", "ruling",
])
_SIG_COMPETITIVE = frozenset([
    "competitor", "competition", "versus", "vs.", "compare", "comparison",
    "alternative", "market share", "ranking", "benchmark", "differentiation",
    "advantage", "position", "landscape", "player", "leader",
])
_SIG_MARKET_INDUSTRY = frozenset([
    "market", "industry", "sector", "market size", "growth", "forecast",
    "trend", "outlook", "adoption", "penetration", "disruption", "segment",
])
_SIG_LEADERSHIP = frozenset([
    "ceo", "founder", "leadership", "executive", "management", "strategy",
    "vision", "roadmap", "board", "chairman", "director", "president",
])
_SIG_NEWS = frozenset([
    "news", "latest", "recent", "today", "announcement", "press release",
    "breaking", "2024", "2025", "2026", "update", "development",
])


def _build_research_tree(
    *,
    query: str,
    depth_tier: str,
    registry_names: list[str],
) -> list[dict]:
    """Decompose any research question into structural branches.

    Works for any domain — science, law, medicine, business, technology,
    geography, social topics, policy, sport, culture, etc. — by detecting
    semantic signals present in the query rather than pattern-matching against
    specific entity types (country, company, industry).

    Returns [{branch_label, sub_question, preferred_providers}].
    Quick tier: 2 branches. Standard+: 4-8 branches. Deep/expert: up to 10.
    """
    lower = query.lower()

    def _b(label: str, sub_q: str) -> dict:
        providers = _BRANCH_PROVIDER_MAP.get(label, ["brave_search", "bing_search"])
        filtered = [p for p in providers if p in registry_names or p in ("brave_search", "bing_search")]
        return {"branch_label": label, "sub_question": sub_q, "preferred_providers": filtered}

    if depth_tier == "quick":
        return [_b("Factual", query), _b("News & Current Events", f"latest news {query}")]

    # ── Detect which optional branches are relevant for this question ─────────
    has_financial    = any(s in lower for s in _SIG_FINANCIAL)
    has_academic     = any(s in lower for s in _SIG_ACADEMIC)
    has_people       = any(s in lower for s in _SIG_PEOPLE_SOCIETY)
    has_policy       = any(s in lower for s in _SIG_POLICY_GOVERNANCE)
    has_tech         = any(s in lower for s in _SIG_TECHNOLOGY)
    has_risk         = any(s in lower for s in _SIG_RISK_SECURITY)
    has_environment  = any(s in lower for s in _SIG_ENVIRONMENT)
    has_legal        = any(s in lower for s in _SIG_LEGAL)
    has_competitive  = any(s in lower for s in _SIG_COMPETITIVE)
    has_market       = any(s in lower for s in _SIG_MARKET_INDUSTRY)
    has_leadership   = any(s in lower for s in _SIG_LEADERSHIP)
    has_news         = any(s in lower for s in _SIG_NEWS)

    is_deep = depth_tier in ("deep_research", "deep_analytics", "expert")
    is_expert = depth_tier == "expert"

    # Always start with the core factual branch
    branches: list[dict] = [_b("Factual", query)]

    # ── Optional branches, ordered by research value ──────────────────────────
    if has_financial or is_deep:
        branches.append(_b("Financial & Economic", f"{query} financial economic data statistics"))
    if has_competitive or is_deep:
        branches.append(_b("Competitive Landscape", f"{query} competitors alternatives comparison market"))
    if has_tech:
        branches.append(_b("Technology & Innovation", f"{query} technology innovation trends developments"))
    if has_people or is_deep:
        branches.append(_b("People & Society", f"{query} population society demographics social impact"))
    if has_policy or is_deep:
        branches.append(_b("Policy & Governance", f"{query} policy regulation government governance"))
    if has_risk:
        branches.append(_b("Risk & Security", f"{query} risks threats security vulnerabilities"))
    if has_environment:
        branches.append(_b("Environment & Sustainability", f"{query} environment climate sustainability"))
    if has_legal:
        branches.append(_b("Legal & Regulatory", f"{query} legal regulatory compliance law"))
    if has_market and not has_competitive:
        branches.append(_b("Market & Industry", f"{query} market size growth forecast industry"))
    if has_leadership:
        branches.append(_b("Leadership & Strategy", f"{query} leadership strategy vision roadmap"))
    if has_academic or is_deep:
        branches.append(_b("Academic Research", f"{query} research study evidence analysis academic"))
    if has_news or True:  # Always include a news branch for current context
        branches.append(_b("News & Current Events", f"latest news {query} 2025 2026"))
    if is_expert:
        branches.append(_b("Expert Opinion", f"{query} expert analysis forecast whitepaper opinion"))

    # For deep tiers with few signal-detected branches, ensure breadth
    if is_deep and len(branches) < 6:
        if not has_market:
            branches.append(_b("Market & Industry", f"{query} market growth trends forecast"))
        if not has_risk:
            branches.append(_b("Risk & Security", f"{query} challenges risks limitations concerns"))

    # Deduplicate (preserve first occurrence) and cap
    seen: set[str] = set()
    unique: list[dict] = []
    for b in branches:
        if b["branch_label"] not in seen:
            seen.add(b["branch_label"])
            unique.append(b)

    max_branches = 10 if is_deep else 8
    return unique[:max_branches]


def _build_provider_plan(
    *,
    depth_tier: str,
    query: str,
    registry_names: list[str],
) -> list[tuple[str, int]]:
    """Return [(connector_id, result_count)] for supplemental source providers.

    Selection is driven by depth tier + keyword signals in the query.
    Only connectors currently registered (env-flag enabled) are included.
    """
    plan: list[tuple[str, int]] = []
    lower = query.lower()

    _ACADEMIC = frozenset([
        "research", "paper", "study", "academic", "machine learning",
        "algorithm", "model", "neural", "science", "theory", "analysis",
        "survey", "review", "journal", "arxiv",
    ])
    _FINANCIAL = frozenset([
        "sec", "edgar", "filing", "10-k", "earnings", "revenue",
        "profit", "financial", "investor", "stock", "ipo",
        "balance sheet", "cash flow", "acquisition", "merger",
    ])

    has_academic = any(sig in lower for sig in _ACADEMIC)
    has_financial = any(sig in lower for sig in _FINANCIAL)
    is_deep = depth_tier in ("deep_research", "deep_analytics", "expert")
    is_standard_plus = depth_tier in ("standard", "deep_research", "deep_analytics", "expert")

    if "arxiv" in registry_names and has_academic and is_standard_plus:
        plan.append(("arxiv", 20 if depth_tier == "expert" else 12 if is_deep else 8))
    if "sec_edgar" in registry_names and has_financial:
        plan.append(("sec_edgar", 12 if is_deep else 6))
    if "newsapi" in registry_names and is_standard_plus:
        plan.append(("newsapi", 14 if is_deep else 8))
    if "reddit" in registry_names and is_deep:
        plan.append(("reddit", 10 if depth_tier == "expert" else 6))

    return plan


class WebResearchTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="marketing.web_research",
        action_class="read",
        risk_level="low",
        required_permissions=["web.read"],
        execution_policy="auto_execute",
        description="Search the web and synthesize source-backed insights.",
    )

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ):
        query = str(params.get("query") or prompt).strip() or "company market research"
        configured_max_variants = context.settings.get("__research_max_query_variants")
        max_query_variants = _as_bounded_int(
            params.get("max_query_variants"),
            default=_as_bounded_int(configured_max_variants, default=8, low=2, high=40),
            low=2,
            high=40,
        )
        configured_results_per_query = context.settings.get("__research_results_per_query")
        results_per_query = _as_bounded_int(
            params.get("results_per_query"),
            default=_as_bounded_int(configured_results_per_query, default=12, low=4, high=30),
            low=4,
            high=30,
        )
        configured_fused_top_k = context.settings.get("__research_fused_top_k")
        fused_top_k = _as_bounded_int(
            params.get("fused_top_k"),
            default=_as_bounded_int(configured_fused_top_k, default=60, low=8, high=600),
            low=8,
            high=600,
        )
        configured_min_sources = context.settings.get("__research_min_unique_sources")
        min_unique_sources = _as_bounded_int(
            params.get("min_unique_sources"),
            default=_as_bounded_int(configured_min_sources, default=15, low=3, high=500),
            low=3,
            high=500,
        )
        configured_search_budget = context.settings.get("__research_web_search_budget")
        requested_search_budget = _as_bounded_int(
            params.get("search_budget"),
            default=_as_bounded_int(
                configured_search_budget,
                default=max_query_variants * results_per_query,
                low=20,
                high=800,
            ),
            low=20,
            high=800,
        )
        max_search_rounds = _as_bounded_int(
            context.settings.get("__research_max_search_rounds"),
            default=1,
            low=1,
            high=4,
        )
        depth_tier = " ".join(str(params.get("research_depth_tier") or context.settings.get("__research_depth_tier") or "standard").split()).strip().lower() or "standard"
        max_live_queries = _as_bounded_int(
            context.settings.get("__research_theater_max_live_queries"),
            default=10,
            low=1,
            high=30,
        )
        max_live_clicks_per_query = _as_bounded_int(
            context.settings.get("__research_theater_clicks_per_query"),
            default=2,
            low=1,
            high=5,
        )
        requested_variants_raw = params.get("query_variants")
        requested_variants = (
            [
                " ".join(str(item).split()).strip()
                for item in requested_variants_raw
                if " ".join(str(item).split()).strip()
            ][:24]
            if isinstance(requested_variants_raw, list)
            else []
        )
        query_variants = _extract_search_variants(
            query=query,
            prompt=prompt,
            requested_variants=requested_variants,
            max_variants=max_query_variants,
        )
        if not query_variants:
            query_variants = [query]
        domain_scope_hosts = _resolve_domain_scope_hosts(
            params=params,
            context_settings=context.settings if isinstance(context.settings, dict) else {},
            query=query,
            query_variants=query_variants,
        )
        domain_scope_mode = _resolve_domain_scope_mode(
            params=params,
            domain_scope_hosts=domain_scope_hosts,
        )
        domain_scope_filtered_out = 0
        search_plan: list[tuple[str, int]] = []
        remaining_budget = requested_search_budget
        for idx, query_variant in enumerate(query_variants):
            variants_left = max(1, len(query_variants) - idx)
            allocated = remaining_budget // variants_left
            if remaining_budget % variants_left:
                allocated += 1
            per_query_limit = max(1, min(results_per_query, allocated))
            search_plan.append((query_variant, per_query_limit))
            remaining_budget = max(0, remaining_budget - per_query_limit)
        planned_result_budget = max(1, sum(limit for _query, limit in search_plan))
        requested_provider = _normalize_search_provider(
            params.get("provider") or params.get("search_provider")
        )
        allow_provider_fallback = _truthy(
            params.get("allow_provider_fallback"),
            default=True,
        )
        sources: list[AgentSource] = []
        bullets: list[str] = []
        trace_events: list[ToolTraceEvent] = []
        started_event = ToolTraceEvent(
            event_type="web_search_started",
            title="Searching online sources",
            detail=f"Query: {_safe_snippet(query, 120)}",
            data={
                "query": query,
                "query_variants": query_variants,
                "provider_requested": requested_provider,
                "research_depth_tier": depth_tier,
                "max_query_variants": max_query_variants,
                "results_per_query": results_per_query,
                "search_budget_requested": requested_search_budget,
                "search_budget_effective": planned_result_budget,
                "fused_top_k": fused_top_k,
                "min_unique_sources": min_unique_sources,
                "domain_scope_hosts": domain_scope_hosts[:6],
                "domain_scope_mode": domain_scope_mode,
            },
        )
        trace_events.append(started_event)
        yield started_event

        # ── S2: Research Tree Decomposition ─────────────────────────────────────
        _rt_registry_names = get_connector_registry().names()
        _research_branches = _build_research_tree(
            query=query,
            depth_tier=depth_tier,
            registry_names=_rt_registry_names,
        )
        if _research_branches:
            tree_started = ToolTraceEvent(
                event_type="research_tree_started",
                title="Building research tree",
                detail=f"Decomposed into {len(_research_branches)} structural branch(es)",
                data={
                    "branch_count": len(_research_branches),
                    "depth_tier": depth_tier,
                    "branches": [b["branch_label"] for b in _research_branches],
                },
            )
            trace_events.append(tree_started)
            yield tree_started
            for _branch in _research_branches:
                _branch_event = ToolTraceEvent(
                    event_type="research_branch_started",
                    title=f"Branch: {_branch['branch_label']}",
                    detail=_safe_snippet(_branch["sub_question"], 120),
                    data={
                        "branch_label": _branch["branch_label"],
                        "sub_question": _branch["sub_question"],
                        "preferred_providers": _branch["preferred_providers"],
                    },
                )
                trace_events.append(_branch_event)
                yield _branch_event

        if domain_scope_mode != "off" and domain_scope_hosts:
            scope_event = ToolTraceEvent(
                event_type="tool_progress",
                title="Apply domain scope to web research",
                detail=f"{domain_scope_mode} scope: {', '.join(domain_scope_hosts[:3])}",
                data=_website_scene_payload(
                    lane="search-domain-scope",
                    primary_index=1,
                    payload={
                        "domain_scope_hosts": domain_scope_hosts[:6],
                        "domain_scope_mode": domain_scope_mode,
                    },
                ),
            )
            trace_events.append(scope_event)
            yield scope_event
        provider_event = ToolTraceEvent(
            event_type="tool_progress",
            title="Select web research provider",
            detail=f"Provider: {requested_provider}",
            data=_website_scene_payload(
                lane="search-provider-select",
                primary_index=1,
                payload={
                    "provider_requested": requested_provider,
                    "provider_fallback_enabled": allow_provider_fallback,
                    "research_depth_tier": depth_tier,
                },
            ),
        )
        trace_events.append(provider_event)
        yield provider_event
        rewrite_event = ToolTraceEvent(
            event_type="retrieval_query_rewrite",
            title="Generate focused search rewrites",
            detail=f"Prepared {len(query_variants)} query variant(s)",
            data={"query_variants": query_variants},
        )
        trace_events.append(rewrite_event)
        yield rewrite_event
        navigate_event = ToolTraceEvent(
            event_type="browser_navigate",
            title="Open search provider",
            detail=f"Submitting {len(query_variants)} rewritten query variant(s) to {requested_provider}",
            data=_website_scene_payload(
                lane="search-provider",
                primary_index=1,
                payload={
                    "query": query,
                    "provider": requested_provider,
                    "query_variants": query_variants,
                },
            ),
        )
        trace_events.append(navigate_event)
        yield navigate_event

        payload: dict[str, Any] = {}
        used_provider = requested_provider
        ok = False
        search_runs: list[dict[str, Any]] = []
        provider_failures: list[dict[str, Any]] = []
        provider_attempted: list[str] = []

        if requested_provider == "brave_search":
            try:
                provider_attempted.append("brave_search")
                trace_events.append(
                    ToolTraceEvent(
                        event_type="api_call_started",
                        title="Call Brave Search API",
                        detail=(
                            f"Running {len(search_plan)} query variant(s) "
                            f"with {planned_result_budget} total result slots"
                        ),
                        data={
                            "provider": "brave_search",
                            "search_budget_requested": requested_search_budget,
                            "search_budget_effective": planned_result_budget,
                        },
                    )
                )
                yield trace_events[-1]
                brave = get_connector_registry().build("brave_search", settings=context.settings)
                for idx, (query_variant, per_query_limit) in enumerate(search_plan, start=1):
                    search_url = _search_results_url("brave_search", query_variant)
                    if idx <= max_live_queries and search_url:
                        live_navigate_event = ToolTraceEvent(
                            event_type="browser_navigate",
                            title=f"Open Brave results {idx}/{len(query_variants)}",
                            detail=_safe_snippet(query_variant, 140),
                            data=_website_scene_payload(
                                lane="search-results-open",
                                primary_index=idx,
                                payload={
                                    "provider": "brave_search",
                                    "query": query_variant,
                                    "variant_index": idx,
                                    "url": search_url,
                                    "source_url": search_url,
                                    "render_quality": "live",
                                },
                            ),
                        )
                        trace_events.append(live_navigate_event)
                        yield live_navigate_event
                    query_event = ToolTraceEvent(
                        event_type="brave.search.query",
                        title=f"Run Brave query {idx}/{len(query_variants)}",
                        detail=_safe_snippet(query_variant, 140),
                        data={
                            "query": query_variant,
                            "variant_index": idx,
                            "provider": "brave_search",
                            "result_limit": per_query_limit,
                        },
                    )
                    trace_events.append(query_event)
                    yield query_event
                    run_payload = brave.web_search(query=query_variant, count=per_query_limit)
                    if not isinstance(run_payload, dict):
                        continue
                    run_payload["query_variant"] = query_variant
                    run_payload["result_limit"] = per_query_limit
                    run_rows = run_payload.get("results") if isinstance(run_payload.get("results"), list) else []
                    scoped_rows, dropped_count = _apply_domain_scope(
                        rows=[row for row in run_rows if isinstance(row, dict)],
                        domain_scope_hosts=domain_scope_hosts,
                        domain_scope_mode=domain_scope_mode,
                    )
                    domain_scope_filtered_out += int(dropped_count)
                    scoped_payload = dict(run_payload)
                    scoped_payload["results"] = scoped_rows
                    search_runs.append(scoped_payload)
                    run_urls = [
                        str(item.get("url") or "")
                        for item in scoped_rows
                        if isinstance(item, dict)
                    ][:5]
                    result_event = ToolTraceEvent(
                        event_type="brave.search.results",
                        title=f"Brave results for query {idx}",
                        detail=f"Captured {len(run_urls)} URL(s) from limit {per_query_limit}",
                        data={
                            "query": query_variant,
                            "top_urls": run_urls,
                            "provider": "brave_search",
                            "result_limit": per_query_limit,
                            "domain_scope_filtered_out": int(dropped_count),
                        },
                    )
                    trace_events.append(result_event)
                    yield result_event
                    if idx <= max_live_queries and search_url:
                        hover_event = ToolTraceEvent(
                            event_type="browser_hover",
                            title=f"Hover search results {idx}/{len(query_variants)}",
                            detail="Reviewing top-ranked result cards",
                            data=_website_scene_payload(
                                lane="search-results-hover",
                                primary_index=idx,
                                payload={
                                    "provider": "brave_search",
                                    "query": query_variant,
                                    "variant_index": idx,
                                    "url": search_url,
                                    "source_url": search_url,
                                },
                            ),
                        )
                        trace_events.append(hover_event)
                        yield hover_event
                        scroll_targets = [14.0, 36.0, 62.0]
                        if len(scoped_rows) >= 8:
                            scroll_count = 3
                        elif len(scoped_rows) >= 4:
                            scroll_count = 2
                        else:
                            scroll_count = 1
                        for scroll_step, scroll_percent in enumerate(scroll_targets[:scroll_count], start=1):
                            scroll_event = ToolTraceEvent(
                                event_type="browser_scroll",
                                title=f"Scroll Brave results {scroll_step}/{scroll_count}",
                                detail=f"Reviewing result cards ({int(round(scroll_percent))}%)",
                                data=_website_scene_payload(
                                    lane="search-results-scroll",
                                    primary_index=idx,
                                    secondary_index=scroll_step,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "url": search_url,
                                        "source_url": search_url,
                                        "scroll_percent": float(scroll_percent),
                                        "scroll_direction": "down",
                                    },
                                ),
                            )
                            trace_events.append(scroll_event)
                            yield scroll_event
                        for rank, clicked_url in enumerate(run_urls[:max_live_clicks_per_query], start=1):
                            if not clicked_url:
                                continue
                            host_label = _hostname_label(clicked_url)
                            result_click_event = ToolTraceEvent(
                                event_type="browser_click",
                                title=f"Click result {rank}",
                                detail=(f"Open {host_label}" if host_label else f"Open result {rank}"),
                                data=_website_scene_payload(
                                    lane="search-result-click",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "selector": f"result_rank_{rank}",
                                        "url": search_url,
                                        "source_url": search_url,
                                        "target_url": clicked_url,
                                    },
                                ),
                            )
                            trace_events.append(result_click_event)
                            yield result_click_event
                            click_event = ToolTraceEvent(
                                event_type="web_result_opened",
                                title=f"Open result {rank}",
                                detail=(f"Opening {host_label}" if host_label else f"Opening result {rank}"),
                                data=_website_scene_payload(
                                    lane="source-opened",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                    },
                                ),
                            )
                            trace_events.append(click_event)
                            yield click_event
                            open_event = ToolTraceEvent(
                                event_type="browser_navigate",
                                title=f"Open source page {rank}",
                                detail=_safe_snippet(clicked_url, 140),
                                data=_website_scene_payload(
                                    lane="source-navigate",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                        "render_quality": "live",
                                    },
                                ),
                            )
                            trace_events.append(open_event)
                            yield open_event
                            source_scroll_percent = min(92.0, 24.0 + (rank * 22.0))
                            source_scroll_event = ToolTraceEvent(
                                event_type="browser_scroll",
                                title=f"Scroll source page {rank}",
                                detail=f"Scanning source evidence ({int(round(source_scroll_percent))}%)",
                                data=_website_scene_payload(
                                    lane="source-scroll",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                        "scroll_percent": float(source_scroll_percent),
                                        "scroll_direction": "down",
                                    },
                                ),
                            )
                            trace_events.append(source_scroll_event)
                            yield source_scroll_event
                            source_preview = ""
                            if rank - 1 < len(scoped_rows) and isinstance(scoped_rows[rank - 1], dict):
                                source_preview = str(
                                    scoped_rows[rank - 1].get("description")
                                    or scoped_rows[rank - 1].get("snippet")
                                    or ""
                                ).strip()
                            extract_event = ToolTraceEvent(
                                event_type="browser_extract",
                                title=f"Extract source evidence {rank}",
                                detail=_safe_snippet(source_preview or clicked_url, 140),
                                data=_website_scene_payload(
                                    lane="source-extract",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                        "text_excerpt": _safe_snippet(source_preview, 260),
                                    },
                                ),
                            )
                            trace_events.append(extract_event)
                            yield extract_event

                fused_results = _fuse_search_results(search_runs, top_k=fused_top_k)
                payload = {"results": fused_results, "query": query, "provider": "brave_fused"}
                used_provider = "brave_search"
                ok = True
                fused_event = ToolTraceEvent(
                    event_type="retrieval_fused",
                    title="Fuse search runs",
                    detail=f"Reduced {sum(len(run.get('results') or []) for run in search_runs)} raw rows to {len(fused_results)} fused results",
                    data={
                        "query_variants": query_variants,
                        "result_count": len(fused_results),
                        "target_source_count": min_unique_sources,
                        "fused_top_k": fused_top_k,
                        "search_budget_requested": requested_search_budget,
                        "search_budget_effective": planned_result_budget,
                        "domain_scope_hosts": domain_scope_hosts[:6],
                        "domain_scope_mode": domain_scope_mode,
                        "domain_scope_filtered_out": int(domain_scope_filtered_out),
                    },
                )
                trace_events.append(fused_event)
                yield fused_event
                trace_events.append(
                    ToolTraceEvent(
                        event_type="api_call_completed",
                        title="Brave Search API completed",
                        detail=f"Collected {len(fused_results)} fused result(s)",
                        data={
                            "provider": "brave_search",
                            "result_count": len(fused_results),
                            "provider_requested": requested_provider,
                        },
                    )
                )
                yield trace_events[-1]
            except Exception as exc:
                failure = _classify_provider_failure(exc)
                failure["provider"] = "brave_search"
                provider_failures.append(failure)
                trace_events.append(
                    ToolTraceEvent(
                        event_type="tool_failed",
                        title="Brave provider failed",
                        detail=f"{failure['reason']}: {failure['message']}",
                        data=failure,
                    )
                )
                yield trace_events[-1]
                ok = False

        # Optional fallback to Bing when Brave fails.
        if not ok and (requested_provider == "bing_search" or allow_provider_fallback):
            try:
                provider_attempted.append("bing_search")
                trace_events.append(
                    ToolTraceEvent(
                        event_type="api_call_started",
                        title="Call Bing Search API",
                        detail="Running fallback search query",
                        data={"provider": "bing_search"},
                    )
                )
                yield trace_events[-1]
                connector = get_connector_registry().build("bing_search", settings=context.settings)
                fallback_count = max(4, min(results_per_query, planned_result_budget))
                payload = connector.search_web(query=query_variants[0], count=fallback_count)
                used_provider = "bing_search"
                trace_events.append(
                    ToolTraceEvent(
                        event_type="tool_progress",
                        title=(
                            "Using Bing provider"
                            if requested_provider == "bing_search"
                            else "Brave unavailable, falling back to Bing"
                        ),
                        detail=(
                            "Using Bing as requested provider"
                            if requested_provider == "bing_search"
                            else "Using Bing as secondary provider"
                        ),
                        data=_website_scene_payload(
                            lane="bing-provider-select",
                            primary_index=1,
                            payload={
                                "query": query_variants[0],
                                "provider": "bing_search",
                                "result_limit": fallback_count,
                            },
                        ),
                    )
                )
                yield trace_events[-1]
                rows = []
                if isinstance(payload, dict):
                    web_pages = payload.get("webPages")
                    rows = web_pages.get("value") if isinstance(web_pages, dict) else []
                scoped_rows, dropped_count = _apply_domain_scope(
                    rows=[row for row in rows if isinstance(row, dict)],
                    domain_scope_hosts=domain_scope_hosts,
                    domain_scope_mode=domain_scope_mode,
                )
                domain_scope_filtered_out += int(dropped_count)
                rows = scoped_rows
                if isinstance(payload, dict):
                    web_pages = payload.get("webPages")
                    if isinstance(web_pages, dict):
                        web_pages["value"] = rows
                bing_query = str(query_variants[0] if query_variants else query).strip() or query
                bing_search_url = _search_results_url("bing_search", bing_query)
                if bing_search_url:
                    bing_nav_event = ToolTraceEvent(
                        event_type="browser_navigate",
                        title="Open Bing results",
                        detail=_safe_snippet(bing_query, 140),
                        data=_website_scene_payload(
                            lane="bing-results-open",
                            primary_index=1,
                            payload={
                                "provider": "bing_search",
                                "query": bing_query,
                                "variant_index": 1,
                                "url": bing_search_url,
                                "source_url": bing_search_url,
                                "render_quality": "live",
                            },
                        ),
                    )
                    trace_events.append(bing_nav_event)
                    yield bing_nav_event
                if isinstance(rows, list) and rows:
                    bing_hover_event = ToolTraceEvent(
                        event_type="browser_hover",
                        title="Hover Bing result cards",
                        detail="Reviewing ranked Bing results",
                        data=_website_scene_payload(
                            lane="bing-results-hover",
                            primary_index=1,
                            payload={
                                "provider": "bing_search",
                                "query": bing_query,
                                "variant_index": 1,
                                "url": bing_search_url,
                                "source_url": bing_search_url,
                            },
                        ),
                    )
                    trace_events.append(bing_hover_event)
                    yield bing_hover_event
                    bing_scroll_event = ToolTraceEvent(
                        event_type="browser_scroll",
                        title="Scroll Bing results",
                        detail="Scanning top Bing results",
                        data=_website_scene_payload(
                            lane="bing-results-scroll",
                            primary_index=1,
                            secondary_index=1,
                            payload={
                                "provider": "bing_search",
                                "query": bing_query,
                                "variant_index": 1,
                                "url": bing_search_url,
                                "source_url": bing_search_url,
                                "scroll_percent": 34.0,
                                "scroll_direction": "down",
                            },
                        ),
                    )
                    trace_events.append(bing_scroll_event)
                    yield bing_scroll_event
                    for rank, row in enumerate(rows[:max_live_clicks_per_query], start=1):
                        if not isinstance(row, dict):
                            continue
                        clicked_url = str(row.get("url") or "").strip()
                        if not clicked_url:
                            continue
                        host_label = _hostname_label(clicked_url)
                        click_event = ToolTraceEvent(
                            event_type="browser_click",
                            title=f"Click Bing result {rank}",
                            detail=(f"Open {host_label}" if host_label else f"Open result {rank}"),
                            data=_website_scene_payload(
                                lane="bing-result-click",
                                primary_index=1,
                                secondary_index=rank,
                                payload={
                                    "provider": "bing_search",
                                    "query": bing_query,
                                    "variant_index": 1,
                                    "result_rank": rank,
                                    "selector": f"result_rank_{rank}",
                                    "url": bing_search_url,
                                    "source_url": bing_search_url,
                                    "target_url": clicked_url,
                                },
                            ),
                        )
                        trace_events.append(click_event)
                        yield click_event
                        open_event = ToolTraceEvent(
                            event_type="web_result_opened",
                            title=f"Open Bing source {rank}",
                            detail=_safe_snippet(clicked_url, 140),
                            data=_website_scene_payload(
                                lane="bing-source-opened",
                                primary_index=1,
                                secondary_index=rank,
                                payload={
                                    "provider": "bing_search",
                                    "query": bing_query,
                                    "variant_index": 1,
                                    "result_rank": rank,
                                    "url": clicked_url,
                                    "source_url": clicked_url,
                                },
                            ),
                        )
                        trace_events.append(open_event)
                        yield open_event
                trace_events.append(
                    ToolTraceEvent(
                        event_type="api_call_completed",
                        title="Bing Search API completed",
                        detail=f"Collected {len(rows) if isinstance(rows, list) else 0} result(s)",
                        data={
                            "provider": "bing_search",
                            "provider_requested": requested_provider,
                        },
                    )
                )
                yield trace_events[-1]
                ok = True
            except Exception as exc:
                failure = _classify_provider_failure(exc)
                failure["provider"] = "bing_search"
                provider_failures.append(failure)
                trace_events.append(
                    ToolTraceEvent(
                        event_type="tool_failed",
                        title="Bing provider failed",
                        detail=f"{failure['reason']}: {failure['message']}",
                        data=failure,
                    )
                )
                yield trace_events[-1]
                ok = False

        if ok:
            trace_events.append(
                ToolTraceEvent(
                    event_type="browser_extract",
                    title="Parse search response",
                    detail="Decoded JSON payload from search provider",
                    data=_website_scene_payload(
                        lane="search-response-parse",
                        primary_index=1,
                        payload={
                            "provider": used_provider,
                            "provider_requested": requested_provider,
                        },
                    ),
                )
            )
            yield trace_events[-1]
        else:
            latest_failure = provider_failures[-1] if provider_failures else {}
            trace_events.append(
                ToolTraceEvent(
                    event_type="tool_failed",
                    title="Search provider unavailable",
                    detail=(
                        f"No data returned from external provider. "
                        f"{str(latest_failure.get('reason') or '').replace('_', ' ')}"
                    ).strip(),
                    data={
                        "provider_requested": requested_provider,
                        "provider_fallback_enabled": allow_provider_fallback,
                        "provider_attempted": provider_attempted[:4],
                        "provider_failures": provider_failures[:4],
                    },
                )
            )
            yield trace_events[-1]

        if ok:
            if used_provider == "brave_search":
                rows = payload.get("results") if isinstance(payload, dict) else []
                results = rows if isinstance(rows, list) else []
                max_source_rows = max(8, min(fused_top_k, 600))
                for item in results[:max_source_rows]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("title") or item.get("url") or "Web result").strip()
                    snippet = str(item.get("description") or item.get("snippet") or "").strip()
                    url = str(item.get("url") or "").strip()
                    excerpt = _safe_snippet(snippet or name or url, 220)
                    if len(bullets) < 24:
                        bullets.append(f"- {name}: {_safe_snippet(snippet or name)}")
                    try:
                        rrf_score = float(item.get("rrf_score") or 0.0)
                    except Exception:
                        rrf_score = 0.0
                    sources.append(
                        AgentSource(
                            source_type="web",
                            label=name,
                            url=url or None,
                            score=max(0.5, min(0.95, 0.68 + (rrf_score * 120))),
                            metadata={
                                "provider": "brave_search",
                                "excerpt": excerpt,
                                "extract": excerpt,
                                "rrf_score": rrf_score,
                            },
                        )
                    )
                quality_event = ToolTraceEvent(
                    event_type="retrieval_quality_assessed",
                    title="Assess retrieval quality",
                    detail=f"Fused retrieval produced {len(results)} result(s); {len(sources)} source(s) selected",
                    data={
                        "provider": "brave_search",
                        "result_count": len(results),
                        "source_count": len(sources),
                        "target_source_count": min_unique_sources,
                        "coverage_ok": len(sources) >= min_unique_sources,
                        "query_variants": query_variants,
                        "domain_scope_hosts": domain_scope_hosts[:6],
                        "domain_scope_mode": domain_scope_mode,
                        "domain_scope_filtered_out": int(domain_scope_filtered_out),
                    },
                )
                trace_events.append(quality_event)
                yield quality_event
            elif used_provider == "bing_search":
                web_pages = payload.get("webPages") if isinstance(payload, dict) else None
                results = web_pages.get("value") if isinstance(web_pages, dict) else []
                max_source_rows = max(8, min(fused_top_k, 600))
                for item in (results or [])[:max_source_rows]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "Web result").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    url = str(item.get("url") or "").strip()
                    excerpt = _safe_snippet(snippet or name or url, 220)
                    if len(bullets) < 24:
                        bullets.append(f"- {name}: {_safe_snippet(snippet or name)}")
                    sources.append(
                        AgentSource(
                            source_type="web",
                            label=name,
                            url=url or None,
                            score=0.74,
                            metadata={
                                "provider": "bing_search",
                                "excerpt": excerpt,
                                "extract": excerpt,
                            },
                        )
                    )
        else:
            bullets.append(
                "- No web search data available. Configure `BRAVE_SEARCH_API_KEY` (required for Brave mode)."
            )

        # ── S1: Supplemental source federation (arxiv, sec_edgar, newsapi, reddit) ─
        if ok:
            _registry = get_connector_registry()
            _sup_plan = _build_provider_plan(
                depth_tier=depth_tier,
                query=query_variants[0] if query_variants else query,
                registry_names=_registry.names(),
            )
            _seen_sup_urls: set[str] = {str(s.url or "") for s in sources}
            for _conn_id, _result_count in _sup_plan:
                try:
                    _connector = _registry.build(_conn_id, settings=context.settings)
                    _sup_start = ToolTraceEvent(
                        event_type="api_call_started",
                        title=f"Query {_conn_id}",
                        detail=_safe_snippet(query_variants[0] if query_variants else query, 120),
                        data={"provider": _conn_id, "result_limit": _result_count},
                    )
                    trace_events.append(_sup_start)
                    yield _sup_start
                    _sup_payload = _connector.search_web(
                        query=query_variants[0] if query_variants else query,
                        count=_result_count,
                    )
                    _sup_rows = _sup_payload.get("results") if isinstance(_sup_payload, dict) else []
                    if not isinstance(_sup_rows, list):
                        _sup_rows = []
                    _sup_done = ToolTraceEvent(
                        event_type="api_call_completed",
                        title=f"{_conn_id} completed",
                        detail=f"{len(_sup_rows)} result(s)",
                        data={"provider": _conn_id, "result_count": len(_sup_rows)},
                    )
                    trace_events.append(_sup_done)
                    yield _sup_done
                    from api.services.agent.research.source_credibility import score_source_credibility
                    for _row in _sup_rows:
                        if not isinstance(_row, dict):
                            continue
                        _url = str(_row.get("url") or "").strip()
                        if not _url or _url in _seen_sup_urls:
                            continue
                        _seen_sup_urls.add(_url)
                        _name = str(_row.get("title") or _url or "Source").strip()
                        _desc = str(_row.get("description") or "").strip()
                        _excerpt = _safe_snippet(_desc or _name or _url, 220)
                        _cred = score_source_credibility(_url)
                        sources.append(
                            AgentSource(
                                source_type="web",
                                label=_name,
                                url=_url or None,
                                score=max(0.5, min(0.98, 0.60 + _cred * 0.40)),
                                credibility_score=_cred,
                                metadata={
                                    "provider": _conn_id,
                                    "excerpt": _excerpt,
                                    "extract": _excerpt,
                                },
                            )
                        )
                        if len(bullets) < 32:
                            bullets.append(f"- {_name}: {_safe_snippet(_desc or _name)}")
                except Exception as _sup_exc:
                    _sup_failure = _classify_provider_failure(_sup_exc)
                    _sup_failure["provider"] = _conn_id
                    provider_failures.append(_sup_failure)

            # ── S2: Emit branch_completed events after all sources are gathered ─
            if _research_branches:
                _total_sources = len(sources)
                _sources_per_branch = max(1, _total_sources // len(_research_branches))
                for _bidx, _branch in enumerate(_research_branches):
                    _branch_done = ToolTraceEvent(
                        event_type="research_branch_completed",
                        title=f"Branch complete: {_branch['branch_label']}",
                        detail=f"~{_sources_per_branch} result(s) contributed",
                        data={
                            "branch_label": _branch["branch_label"],
                            "result_count": _sources_per_branch,
                            "preferred_providers": _branch["preferred_providers"],
                        },
                    )
                    trace_events.append(_branch_done)
                    yield _branch_done

        # ── T3: Emit evidence_crystallized for top sources ─────────────────────
        _crystal_cap = 4 if depth_tier in ("deep_research", "deep_analytics", "expert") else 2
        _crystal_count = 0
        for _src in sources:
            if _crystal_count >= _crystal_cap:
                break
            _src_score = float(getattr(_src, "score", 0.0) or 0.0)
            if _src_score < 0.72:
                continue
            _src_label = str(getattr(_src, "label", "") or "").strip()
            _src_url = str(getattr(_src, "url", "") or "").strip()
            _src_excerpt = str((getattr(_src, "metadata", {}) or {}).get("excerpt", "") or "").strip()
            _crystal_event = ToolTraceEvent(
                event_type="evidence_crystallized",
                title=f"Evidence found: {_src_label[:48] or _src_url[:48]}",
                detail=_safe_snippet(_src_excerpt or _src_label, 120),
                data={
                    "source_name": _src_label,
                    "source_url": _src_url,
                    "extract": _safe_snippet(_src_excerpt, 120),
                    "strength_score": round(_src_score, 3),
                    "provider": (getattr(_src, "metadata", {}) or {}).get("provider", used_provider),
                    "highlight_regions": [
                        {"x": 8, "y": 20, "width": 84, "height": 12, "color": "gold"}
                    ],
                },
            )
            trace_events.append(_crystal_event)
            yield _crystal_event
            _crystal_count += 1

        # ── T4: Emit trust_score_updated after sources are crystallized ─────────
        if sources:
            _scores = [float(getattr(s, "score", 0.0) or 0.0) for s in sources]
            _avg_trust = round(sum(_scores) / len(_scores), 3)
            _gate = "green" if _avg_trust >= 0.80 else "amber" if _avg_trust >= 0.55 else "red"
            _contested = sum(1 for s in sources if float(getattr(s, "score", 0.0) or 0.0) < 0.60)
            _trust_event = ToolTraceEvent(
                event_type="trust_score_updated",
                title="Trust score updated",
                detail=f"Source credibility: {_gate} ({_avg_trust:.2f})",
                data={
                    "trust_score": _avg_trust,
                    "gate_color": _gate,
                    "reason": f"{len(sources)} sources evaluated; {_contested} low-credibility",
                    "source_count": len(sources),
                },
            )
            trace_events.append(_trust_event)
            yield _trust_event

        if bullets:
            highlight_terms = []
            for source in sources[:6]:
                label = str(source.label or "").strip()
                if label:
                    highlight_terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", label))
            dedup_terms = []
            for term in highlight_terms:
                lowered = term.lower()
                if lowered not in dedup_terms:
                    dedup_terms.append(lowered)
                if len(dedup_terms) >= 8:
                    break
            if dedup_terms:
                highlight_event = ToolTraceEvent(
                    event_type="browser_keyword_highlight",
                    title="Highlight search keywords",
                    detail=", ".join(dedup_terms[:6]),
                    data={"keywords": dedup_terms[:8]},
                )
                trace_events.append(highlight_event)
                yield highlight_event
            snippet_text = _safe_snippet(" | ".join(bullets), 320)
            if snippet_text:
                copy_event = ToolTraceEvent(
                    event_type="clipboard_copy",
                    title="Copy web snippets",
                    detail=snippet_text,
                    data={"clipboard_text": snippet_text},
                )
                trace_events.append(copy_event)
                yield copy_event

        unique_urls = list(
            dict.fromkeys(
                [str(source.url or "").strip() for source in sources if str(source.url or "").strip()]
            )
        )
        if len(unique_urls) < min_unique_sources:
            shortfall_event = ToolTraceEvent(
                event_type="tool_progress",
                title="Research coverage shortfall detected",
                detail=(
                    f"Collected {len(unique_urls)} unique sources; target is {min_unique_sources}. "
                    "Continue with additional targeted queries."
                ),
                data=_website_scene_payload(
                    lane="research-coverage-check",
                    primary_index=max(1, len(unique_urls)),
                    secondary_index=max(1, min_unique_sources),
                    payload={
                        "source_count": len(unique_urls),
                        "target_source_count": min_unique_sources,
                        "coverage_ok": False,
                        "domain_scope_hosts": domain_scope_hosts[:6],
                        "domain_scope_mode": domain_scope_mode,
                    },
                ),
            )
            trace_events.append(shortfall_event)
            yield shortfall_event

        # ── Iterative gap-fill rounds ─────────────────────────────────────────
        # For deep_research / expert tiers (max_search_rounds ≥ 2), run up to
        # (max_search_rounds - 1) additional targeted search passes when coverage
        # is below the minimum.  Each round extracts topics from the top sources
        # collected so far and fires gap-fill queries for them.
        if ok and max_search_rounds >= 2 and len(unique_urls) < min_unique_sources:
            _seen_gap_urls: set[str] = set(unique_urls)
            _gap_round_limit = max_search_rounds - 1  # round 1 already done above

            for _gap_round in range(1, _gap_round_limit + 1):
                # Coverage already met by a previous gap round — stop early.
                if len(_seen_gap_urls) >= min_unique_sources:
                    break

                # Extract salient named terms from top-scoring source labels / excerpts
                # as gap-fill query seeds (no LLM call — fast entity extraction).
                _top_labels = [
                    str(getattr(s, "label", "") or "").strip()
                    for s in sorted(sources, key=lambda x: float(getattr(x, "score", 0) or 0), reverse=True)[:10]
                ]
                _top_excerpts = [
                    str((getattr(s, "metadata", {}) or {}).get("excerpt", "") or "").strip()
                    for s in sources[:6]
                ]
                _all_terms: list[str] = []
                for _text in _top_labels + _top_excerpts:
                    _all_terms.extend(re.findall(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,3}\b", _text))
                _unique_terms: list[str] = []
                _seen_t: set[str] = set()
                for _t in _all_terms:
                    _lt = _t.lower()
                    if _lt not in _seen_t and _lt not in query.lower():
                        _seen_t.add(_lt)
                        _unique_terms.append(_t)
                    if len(_unique_terms) >= 6:
                        break

                if not _unique_terms:
                    break

                _gap_queries = [f"{query} {_t}" for _t in _unique_terms[:4]]
                _gap_budget = max(results_per_query, min(20, min_unique_sources - len(_seen_gap_urls)))

                _gap_start = ToolTraceEvent(
                    event_type="tool_progress",
                    title=f"Gap-fill search round {_gap_round + 1}",
                    detail=f"Targeting {len(_gap_queries)} topic angles to fill {min_unique_sources - len(_seen_gap_urls)} source gap",
                    data={
                        "gap_round": _gap_round + 1,
                        "gap_queries": _gap_queries[:4],
                        "target_additional": min_unique_sources - len(_seen_gap_urls),
                    },
                )
                trace_events.append(_gap_start)
                yield _gap_start

                _gap_search_runs: list[dict[str, Any]] = []
                for _gq in _gap_queries:
                    try:
                        _gap_connector = get_connector_registry().build("brave_search", settings=context.settings)
                        _gap_payload = _gap_connector.search_web(query=_gq, count=_gap_budget)
                        if isinstance(_gap_payload, dict):
                            _gap_search_runs.append({"query": _gq, "results": _gap_payload.get("results") or []})
                    except Exception:
                        pass

                if _gap_search_runs:
                    _gap_fused = _fuse_search_results(_gap_search_runs, top_k=_gap_budget * len(_gap_queries))
                    for _gr in _gap_fused:
                        if not isinstance(_gr, dict):
                            continue
                        _gurl = str(_gr.get("url") or "").strip()
                        if not _gurl or _gurl in _seen_gap_urls:
                            continue
                        _seen_gap_urls.add(_gurl)
                        _gname = str(_gr.get("title") or _gurl or "Web result").strip()
                        _gsnippet = str(_gr.get("description") or _gr.get("snippet") or "").strip()
                        _gexcerpt = _safe_snippet(_gsnippet or _gname, 220)
                        try:
                            _grrf = float(_gr.get("rrf_score") or 0.0)
                        except Exception:
                            _grrf = 0.0
                        sources.append(
                            AgentSource(
                                source_type="web",
                                label=_gname,
                                url=_gurl or None,
                                score=max(0.5, min(0.92, 0.62 + (_grrf * 100))),
                                metadata={
                                    "provider": "brave_search_gap",
                                    "excerpt": _gexcerpt,
                                    "extract": _gexcerpt,
                                    "gap_round": _gap_round + 1,
                                },
                            )
                        )
                        if len(bullets) < 48:
                            bullets.append(f"- {_gname}: {_safe_snippet(_gsnippet or _gname)}")

                _gap_done = ToolTraceEvent(
                    event_type="tool_progress",
                    title=f"Gap-fill round {_gap_round + 1} complete",
                    detail=f"Now at {len(_seen_gap_urls)} unique sources (target: {min_unique_sources})",
                    data={
                        "gap_round": _gap_round + 1,
                        "source_count_now": len(_seen_gap_urls),
                        "target_source_count": min_unique_sources,
                        "coverage_ok": len(_seen_gap_urls) >= min_unique_sources,
                    },
                )
                trace_events.append(_gap_done)
                yield _gap_done

            # Refresh unique_urls after gap-fill passes
            unique_urls = list(
                dict.fromkeys(
                    [str(source.url or "").strip() for source in sources if str(source.url or "").strip()]
                )
            )

        content = "\n".join(bullets)
        summary = (
            f"Collected {len(sources)} web sources ({len(unique_urls)} unique URLs) "
            f"using {used_provider}: {query}"
        )
        if sources:
            context.settings["__latest_web_sources"] = [
                source.to_dict()
                for source in sources[:200]
            ]
            context.settings["__latest_web_query"] = query
            context.settings["__latest_web_provider"] = used_provider
            context.settings["__latest_web_source_count"] = len(unique_urls)
            context.settings["__latest_web_source_target"] = min_unique_sources
            context.settings["__latest_research_depth_tier"] = depth_tier
            context.settings["__latest_web_domain_scope_hosts"] = domain_scope_hosts[:6]
            context.settings["__latest_web_domain_scope_mode"] = domain_scope_mode
            context.settings["__latest_web_domain_scope_filtered_out"] = int(domain_scope_filtered_out)
        next_steps = [
            "Validate top 2 sources against internal company data.",
            "Convert findings into a competitor/market briefing.",
        ]
        if len(unique_urls) < min_unique_sources:
            next_steps.insert(
                0,
                f"Run another research pass to reach at least {min_unique_sources} unique sources.",
            )
        return ToolExecutionResult(
            summary=summary,
            content=content,
            data={
                "query": query,
                "query_variants": query_variants,
                "max_query_variants": max_query_variants,
                "results_per_query": results_per_query,
                "search_budget_requested": requested_search_budget,
                "search_budget_effective": planned_result_budget,
                "fused_top_k": fused_top_k,
                "research_depth_tier": depth_tier,
                "provider": used_provider,
                "provider_requested": requested_provider,
                "provider_fallback_enabled": allow_provider_fallback,
                "provider_attempted": provider_attempted[:4],
                "provider_failures": provider_failures[:4],
                "source_count": len(sources),
                "unique_source_count": len(unique_urls),
                "min_unique_sources": min_unique_sources,
                "coverage_ok": len(unique_urls) >= min_unique_sources,
                "items": [source.to_dict() for source in sources],
                "domain_scope_hosts": domain_scope_hosts[:6],
                "domain_scope_mode": domain_scope_mode,
                "domain_scope_filtered_out": int(domain_scope_filtered_out),
            },
            sources=sources,
            next_steps=next_steps,
            events=trace_events,
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        stream = self.execute_stream(context=context, prompt=prompt, params=params)
        trace_events: list[ToolTraceEvent] = []
        while True:
            try:
                trace_events.append(next(stream))
            except StopIteration as stop:
                result = stop.value
                break
        result.events = trace_events
        return result


class CompetitorProfileTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="marketing.competitor_profile",
        action_class="draft",
        risk_level="low",
        required_permissions=["analysis.write"],
        execution_policy="auto_execute",
        description="Build a concise competitor profile from provided context.",
    )

    _COMPETITOR_RE = re.compile(r"\b(versus|vs\.?|against)\s+([A-Za-z0-9 ._-]+)", re.IGNORECASE)

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        competitor = str(params.get("competitor") or "").strip()
        if not competitor:
            match = self._COMPETITOR_RE.search(prompt)
            if match:
                competitor = match.group(2).strip()
        if not competitor:
            competitor = "Competitor"

        positioning = params.get("positioning") or "Positioning is not yet validated."
        pricing = params.get("pricing") or "Pricing signals need verified source data."
        channels = params.get("channels") or "Channel mix unknown."

        content = (
            f"### Competitor Profile: {html.escape(competitor)}\n"
            f"- Positioning: {positioning}\n"
            f"- Pricing signals: {pricing}\n"
            f"- Distribution/marketing channels: {channels}\n"
            "- Key gap to exploit: emphasize measurable outcomes + faster execution."
        )
        return ToolExecutionResult(
            summary=f"Drafted competitor profile for {competitor}.",
            content=content,
            data={"competitor": competitor},
            sources=[],
            next_steps=[
                "Attach at least 3 verifiable sources for pricing and claims.",
                "Run messaging A/B draft recommendations.",
            ],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Assemble competitor profile",
                    detail=f"Structured profile generated for {competitor}",
                    data={"competitor": competitor},
                )
            ],
        )
