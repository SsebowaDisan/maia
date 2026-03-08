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

from urllib.parse import urlparse

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
    """
    Return a credibility score in [0.0, 1.0] for a given URL.

    Uses a domain lookup table first. Falls back to TLD heuristics for
    unknown domains. Never makes external calls.
    """
    if not url or not isinstance(url, str):
        return _DEFAULT_SCORE

    domain = _extract_domain(url)
    if not domain:
        return _DEFAULT_SCORE

    # Exact match
    exact = _DOMAIN_TABLE.get(domain)
    if exact is not None:
        return exact

    # Suffix match (handles subdomains like news.bbc.com)
    for suffix, score in _DOMAIN_TABLE.items():
        if domain.endswith(f".{suffix}") or domain == suffix:
            return score

    # TLD-based fallback
    for tld, score in _TLD_SCORES.items():
        if domain.endswith(tld):
            return score

    return _DEFAULT_SCORE


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
    "build_credibility_weights",
    "score_source_credibility",
]
