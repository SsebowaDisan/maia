from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus, urlparse

from api.services.agent.tools.research_helpers import truthy as _truthy
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
    # strict mode yielded no matches — fall back gracefully rather than returning
    # an empty list that would silently kill coverage.  Prefer mode returns all
    # rows; strict mode now degrades to prefer rather than returning nothing.
    return rows, 0


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
    branching_mode: str = "segmented",
) -> list[dict]:
    """Decompose a research question into optional structural branches.

    overview mode keeps standard requests on a single evidence track.
    segmented mode expands into structural branches when breadth is justified.
    """
    lower = query.lower()
    normalized_branching_mode = " ".join(str(branching_mode or "").split()).strip().lower()
    if normalized_branching_mode not in {"overview", "segmented"}:
        normalized_branching_mode = "segmented"

    def _b(label: str, sub_q: str) -> dict:
        providers = _BRANCH_PROVIDER_MAP.get(label, ["brave_search", "bing_search"])
        filtered = [p for p in providers if p in registry_names or p in ("brave_search", "bing_search")]
        return {"branch_label": label, "sub_question": sub_q, "preferred_providers": filtered}

    if depth_tier == "quick":
        return [_b("Factual", query)]

    has_financial = any(s in lower for s in _SIG_FINANCIAL)
    has_academic = any(s in lower for s in _SIG_ACADEMIC)
    has_people = any(s in lower for s in _SIG_PEOPLE_SOCIETY)
    has_policy = any(s in lower for s in _SIG_POLICY_GOVERNANCE)
    has_tech = any(s in lower for s in _SIG_TECHNOLOGY)
    has_risk = any(s in lower for s in _SIG_RISK_SECURITY)
    has_environment = any(s in lower for s in _SIG_ENVIRONMENT)
    has_legal = any(s in lower for s in _SIG_LEGAL)
    has_competitive = any(s in lower for s in _SIG_COMPETITIVE)
    has_market = any(s in lower for s in _SIG_MARKET_INDUSTRY)
    has_leadership = any(s in lower for s in _SIG_LEADERSHIP)
    has_news = any(s in lower for s in _SIG_NEWS)

    is_deep = depth_tier in ("deep_research", "deep_analytics", "expert")
    is_expert = depth_tier == "expert"

    if normalized_branching_mode == "overview" and not is_deep:
        return [_b("Factual", query)]

    branches: list[dict] = [_b("Factual", query)]
    if has_financial or is_deep:
        branches.append(_b("Financial & Economic", f"{query} financial economic data statistics"))
    if has_competitive or is_deep:
        branches.append(_b("Competitive Landscape", f"{query} competitors alternatives comparison market"))
    if has_tech and is_deep:
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
    if has_academic and (normalized_branching_mode == "segmented" or is_deep):
        branches.append(_b("Academic Research", f"{query} research study evidence analysis academic"))
    if has_news and (normalized_branching_mode == "segmented" or is_deep):
        branches.append(_b("News & Current Events", f"latest news {query} 2025 2026"))
    if is_expert:
        branches.append(_b("Expert Opinion", f"{query} expert analysis forecast whitepaper opinion"))

    if is_deep and len(branches) < 6:
        if not has_market:
            branches.append(_b("Market & Industry", f"{query} market growth trends forecast"))
        if not has_risk:
            branches.append(_b("Risk & Security", f"{query} challenges risks limitations concerns"))

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
    branching_mode: str = "segmented",
) -> list[tuple[str, int]]:
    """Return [(connector_id, result_count)] for supplemental source providers."""
    plan: list[tuple[str, int]] = []
    lower = query.lower()
    normalized_branching_mode = " ".join(str(branching_mode or "").split()).strip().lower()
    if normalized_branching_mode not in {"overview", "segmented"}:
        normalized_branching_mode = "segmented"

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
    _NEWS = frozenset([
        "news", "latest", "recent", "today", "announcement", "update", "2024", "2025", "2026",
    ])

    has_academic = any(sig in lower for sig in _ACADEMIC)
    has_financial = any(sig in lower for sig in _FINANCIAL)
    has_news = any(sig in lower for sig in _NEWS)
    is_deep = depth_tier in ("deep_research", "deep_analytics", "expert")
    is_standard_plus = depth_tier in ("standard", "deep_research", "deep_analytics", "expert")

    if "arxiv" in registry_names and has_academic and is_standard_plus:
        plan.append(("arxiv", 20 if depth_tier == "expert" else 12 if is_deep else 8))
    if "sec_edgar" in registry_names and has_financial:
        plan.append(("sec_edgar", 12 if is_deep else 6))
    if "newsapi" in registry_names and (has_news or is_deep or normalized_branching_mode == "segmented"):
        plan.append(("newsapi", 14 if is_deep else 8))
    if "reddit" in registry_names and is_deep:
        plan.append(("reddit", 10 if depth_tier == "expert" else 6))

    return plan

