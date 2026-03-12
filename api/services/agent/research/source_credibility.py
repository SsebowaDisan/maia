from __future__ import annotations

"""
Source credibility scoring for research federation.

Scores are in [0.0, 1.0]:
  0.9+  High credibility: peer-reviewed, government, established newswires
  0.6   Medium: established publications, Wikipedia, corporate sites
  0.3   Low: social platforms, forums, unknown blogs

The lookup table covers the top domains by traffic and trust signal.
For unknown domains the heuristic uses TLD and subdomain patterns.
"""

import re
from urllib.parse import urlparse

from api.services.agent.llm_runtime import call_json_response, env_bool

_HIGH: float = 0.92
_MED_HIGH: float = 0.78
_MEDIUM: float = 0.62
_MED_LOW: float = 0.45
_LOW: float = 0.30

# (domain_suffix → score).  Longest match wins.
_DOMAIN_TABLE: dict[str, float] = {
    # Academic / preprint
    "arxiv.org": _HIGH,
    "scholar.google.com": _HIGH,
    "semanticscholar.org": _HIGH,
    "pubmed.ncbi.nlm.nih.gov": _HIGH,
    "ncbi.nlm.nih.gov": _HIGH,
    "jstor.org": _HIGH,
    "sciencedirect.com": _HIGH,
    "nature.com": _HIGH,
    "springer.com": _HIGH,
    "wiley.com": _HIGH,
    "tandfonline.com": _HIGH,
    "ssrn.com": _HIGH,
    "acm.org": _HIGH,
    "ieee.org": _HIGH,
    "researchgate.net": _MED_HIGH,
    # Government & regulatory
    "sec.gov": _HIGH,
    "ftc.gov": _HIGH,
    "irs.gov": _HIGH,
    "cdc.gov": _HIGH,
    "fda.gov": _HIGH,
    "europa.eu": _HIGH,
    "eur-lex.europa.eu": _HIGH,
    "who.int": _HIGH,
    "un.org": _HIGH,
    "worldbank.org": _HIGH,
    "imf.org": _HIGH,
    "oecd.org": _HIGH,
    "bls.gov": _HIGH,
    "census.gov": _HIGH,
    # Established newswires & financial press
    "reuters.com": _HIGH,
    "apnews.com": _HIGH,
    "ft.com": _HIGH,
    "wsj.com": _HIGH,
    "bloomberg.com": _MED_HIGH,
    "economist.com": _MED_HIGH,
    "nytimes.com": _MED_HIGH,
    "theguardian.com": _MED_HIGH,
    "bbc.com": _MED_HIGH,
    "bbc.co.uk": _MED_HIGH,
    "npr.org": _MED_HIGH,
    "washingtonpost.com": _MED_HIGH,
    "cnbc.com": _MED_HIGH,
    "marketwatch.com": _MED_HIGH,
    "barrons.com": _MED_HIGH,
    "forbes.com": _MEDIUM,
    "businessinsider.com": _MEDIUM,
    "techcrunch.com": _MEDIUM,
    "wired.com": _MEDIUM,
    "arstechnica.com": _MEDIUM,
    "zdnet.com": _MEDIUM,
    "cnn.com": _MEDIUM,
    "time.com": _MEDIUM,
    "axios.com": _MEDIUM,
    "politico.com": _MEDIUM,
    "theatlantic.com": _MEDIUM,
    "vox.com": _MEDIUM,
    # Reference
    "wikipedia.org": _MEDIUM,
    "britannica.com": _MEDIUM,
    "investopedia.com": _MEDIUM,
    # Social / forums (low)
    "reddit.com": _LOW,
    "twitter.com": _LOW,
    "x.com": _LOW,
    "facebook.com": _LOW,
    "linkedin.com": _MED_LOW,
    "quora.com": _LOW,
    "stackexchange.com": _MED_LOW,
    "stackoverflow.com": _MED_LOW,
    "hackernews.ycombinator.com": _MED_LOW,
    "news.ycombinator.com": _MED_LOW,
    "medium.com": _MED_LOW,
    "substack.com": _MED_LOW,
}

# TLD-based heuristic scores (lower confidence)
_TLD_SCORES: dict[str, float] = {
    ".gov": _HIGH,
    ".edu": _MED_HIGH,
    ".int": _HIGH,
    ".org": _MEDIUM,
    ".com": _MEDIUM,
    ".net": _MED_LOW,
    ".io": _MED_LOW,
    ".co": _MED_LOW,
}

_DEFAULT_SCORE: float = _MED_LOW

# Known disinformation / coordinated-inauthentic-behaviour domains.
# These are scored at floor (0.05) regardless of TLD or other signals.
_DISINFORMATION_DOMAINS: frozenset[str] = frozenset([
    "infowars.com",
    "naturalnews.com",
    "beforeitsnews.com",
    "zerohedge.com",
    "thegatewaypundit.com",
    "worldnewsdailyreport.com",
    "yournewswire.com",
    "newspunch.com",
    "amplifyingglass.com",
    "conservativedailypost.com",
    "americanpatriotdaily.com",
    "realnewsrightnow.com",
    "abcnews.com.co",
    "cbsnews.com.co",
    "nbcnews.com.co",
    "empirenews.net",
    "huzlers.com",
    "nationalreport.net",
    "theonion.com",        # satire — keep near-zero so it doesn't surface as fact
    "clickhole.com",       # satire
    "babylonbee.com",      # satire
    "stuppid.com",
    "naha24.net",
    "eutimes.net",
])

_DISINFO_SCORE: float = 0.05


def _score_unknown_domain_llm(domain: str) -> float | None:
    """Ask the LLM to estimate the credibility of an unrecognised domain.

    Returns a float in [0.0, 1.0] or None when the feature is disabled or
    the call fails.  Results are NOT cached — callers should only invoke this
    when a domain is genuinely unknown and LLM scoring is enabled.
    """
    if not env_bool("MAIA_AGENT_LLM_DOMAIN_CREDIBILITY_ENABLED", default=True):
        return None
    if not domain or len(domain) > 253:
        return None
    response = call_json_response(
        system_prompt=(
            "You assess the credibility of web domains for an enterprise research agent. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Rate the credibility of the following domain as an information source.\n"
            "Consider: is it a peer-reviewed publisher, major news outlet, government site, "
            "established trade publication, known disinformation site, low-quality blog, or unknown?\n"
            "Return JSON only:\n"
            '{ "score": 0.62, "reason": "established trade publication" }\n'
            "Score guide: 0.9+=peer-reviewed/gov; 0.7-0.9=major news/established; "
            "0.5-0.7=trade/niche pub; 0.3-0.5=blog/forum; 0.0-0.3=disinfo/satire/unknown.\n\n"
            f"Domain: {domain}"
        ),
        temperature=0.0,
        timeout_seconds=8,
        max_tokens=80,
    )
    if not isinstance(response, dict):
        return None
    try:
        val = float(response.get("score", -1))
        if 0.0 <= val <= 1.0:
            return val
    except Exception:
        pass
    return None


def _extract_domain(url: str) -> str:
    """Return registered domain in lowercase, no www."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        host = url.lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(":")[0]  # strip port


def score_source_credibility(url: str) -> float:
    """Return a credibility score in [0.0, 1.0] for a given URL.

    Resolution order:
    1. Disinformation domain list → floor score (0.05)
    2. Domain lookup table (exact + suffix match)
    3. TLD heuristic
    4. LLM-based scoring for genuinely unknown domains (opt-in via env flag)
    5. Default score
    """
    if not url or not isinstance(url, str):
        return _DEFAULT_SCORE

    domain = _extract_domain(url)
    if not domain:
        return _DEFAULT_SCORE

    # 1. Hard-block known disinformation / satire domains
    if domain in _DISINFORMATION_DOMAINS:
        return _DISINFO_SCORE
    for disinfo in _DISINFORMATION_DOMAINS:
        if domain.endswith(f".{disinfo}") or domain == disinfo:
            return _DISINFO_SCORE

    # 2. Exact match in trust table
    exact = _DOMAIN_TABLE.get(domain)
    if exact is not None:
        return exact

    # 3. Suffix match (handles subdomains like news.bbc.com)
    for suffix, score in _DOMAIN_TABLE.items():
        if domain.endswith(f".{suffix}") or domain == suffix:
            return score

    # 4. TLD-based heuristic
    tld_score: float | None = None
    for tld, score in _TLD_SCORES.items():
        if domain.endswith(tld):
            tld_score = score
            break

    # 5. LLM scoring for unknown domains — only invoked when the domain is
    #    truly unrecognised (no table or TLD hit) so calls are rare.
    if tld_score is None:
        llm_score = _score_unknown_domain_llm(domain)
        if llm_score is not None:
            return llm_score

    return tld_score if tld_score is not None else _DEFAULT_SCORE


_CURRENT_YEAR: int = 2026
# Matches 4-digit years in the range 2000–2029 inside URLs and text snippets.
_YEAR_RE = re.compile(r"\b(20[0-2][0-9])\b")

# Freshness decay table: years_ago → multiplier [0.3, 1.0].
# Recent content gets full weight; older content degrades gradually.
_FRESHNESS_TABLE: dict[int, float] = {
    0: 1.00,  # current year
    1: 0.95,
    2: 0.88,
    3: 0.78,
    4: 0.65,
    5: 0.52,
    6: 0.42,
    7: 0.35,
}
_FRESHNESS_FLOOR: float = 0.30


def _extract_year(url: str, snippet: str) -> int | None:
    """Extract the most recent plausible publication year from a URL or text snippet."""
    candidates: list[int] = []
    for text in (url, snippet):
        for m in _YEAR_RE.finditer(str(text or "")):
            try:
                y = int(m.group(1))
                if 2000 <= y <= _CURRENT_YEAR:
                    candidates.append(y)
            except ValueError:
                pass
    return max(candidates) if candidates else None


def score_source_freshness(url: str, snippet: str = "") -> float:
    """Return a freshness multiplier in [0.3, 1.0] based on publication year.

    Extracts the year from the URL path or snippet text.  When no year is
    found, returns a neutral 0.75 so undated sources are not penalised
    heavily but still rank below recent, dated ones.
    """
    year = _extract_year(url, snippet)
    if year is None:
        return 0.65  # mild penalty for undated pages — ranked below dated sources
    years_ago = max(0, _CURRENT_YEAR - year)
    return _FRESHNESS_TABLE.get(years_ago, _FRESHNESS_FLOOR)


def apply_freshness_weight(
    credibility_score: float,
    freshness_score: float,
    *,
    freshness_weight: float = 0.25,
) -> float:
    """Blend credibility and freshness into a composite score in [0.0, 1.0].

    freshness_weight=0.25 means the final score is 75% credibility + 25% freshness,
    preserving credibility as the primary signal while rewarding recency.
    """
    w = max(0.0, min(1.0, float(freshness_weight)))
    composite = (1.0 - w) * float(credibility_score) + w * float(freshness_score)
    return round(max(0.0, min(1.0, composite)), 4)


def build_credibility_weights(results: list[dict]) -> dict[str, float]:
    """
    Build a {domain: score} map for a list of search result dicts.

    Each dict must have a "url" key. Used to pass into fuse_search_results()
    as source_weights.
    """
    weights: dict[str, float] = {}
    for item in results:
        url = str(item.get("url") or "")
        if not url:
            continue
        domain = _extract_domain(url)
        if domain and domain not in weights:
            weights[domain] = score_source_credibility(url)
    return weights


__all__ = [
    "apply_freshness_weight",
    "build_credibility_weights",
    "score_source_credibility",
    "score_source_freshness",
]
