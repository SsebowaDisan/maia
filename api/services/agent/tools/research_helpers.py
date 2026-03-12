from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

# Tracking/campaign query parameters stripped before URL deduplication.
_TRACKING_PARAMS: frozenset[str] = frozenset([
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "fbclid", "gclid", "msclkid", "ref", "source",
    "via", "_hsenc", "_hsmi", "mc_cid", "mc_eid", "ncid", "cid", "sid",
    "yclid", "twclid", "igshid", "dclid", "wbraid", "gbraid",
])


def normalize_url_for_dedup(url: str) -> str:
    """Normalize a URL for deduplication.

    Strips tracking params, canonicalizes scheme (http→https), removes www,
    strips default ports, removes trailing path slashes.  Two URLs pointing
    to the same content produce the same key.
    """
    raw = str(url or "").strip()
    if not raw:
        return raw
    try:
        parsed = urlparse(raw)
        scheme = "https" if parsed.scheme in ("http", "https") else parsed.scheme
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if netloc.endswith(":80") or netloc.endswith(":443"):
            netloc = netloc.rsplit(":", 1)[0]
        path = parsed.path.rstrip("/") or "/"
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=False)
            clean = {k: v for k, v in params.items() if k.lower() not in _TRACKING_PARAMS}
            clean_query = urlencode({k: v[0] for k, v in sorted(clean.items())}) if clean else ""
        else:
            clean_query = ""
        return urlunparse((scheme, netloc, path, "", clean_query, ""))
    except Exception:
        return raw


def normalize_result_row(row: dict[str, Any], *, provider: str = "unknown") -> dict[str, Any]:
    """Normalize a search result from any provider into a common schema.

    Handles field name differences across Brave, Bing, ArXiv, NewsAPI, SEC EDGAR.
    Output keys: title, url, description, date, source, authors, provider, score.
    """
    if not isinstance(row, dict):
        return {}
    title = str(
        row.get("title") or row.get("name") or row.get("headline") or ""
    ).strip()
    url = str(
        row.get("url") or row.get("link") or row.get("href") or ""
    ).strip()
    description = str(
        row.get("description") or row.get("snippet") or row.get("abstract")
        or row.get("summary") or row.get("body") or row.get("content") or ""
    ).strip()
    date = str(
        row.get("date") or row.get("published_date") or row.get("publishedAt")
        or row.get("published") or row.get("datePublished") or row.get("updated") or ""
    ).strip()
    source = str(
        row.get("source") or row.get("domain") or row.get("publisher")
        or row.get("outlet") or ""
    ).strip()
    authors_raw = row.get("authors") or row.get("author") or []
    if isinstance(authors_raw, str):
        authors: list[str] = [authors_raw] if authors_raw.strip() else []
    elif isinstance(authors_raw, list):
        authors = [str(a).strip() for a in authors_raw if str(a).strip()][:5]
    else:
        authors = []
    score: float | None = None
    for score_key in ("relevance_score", "score", "rrf_score", "rank_score", "relevance"):
        val = row.get(score_key)
        if val is not None:
            try:
                score = float(val)
                break
            except Exception:
                pass
    return {
        "title": title,
        "url": url,
        "description": description,
        "date": date,
        "source": source,
        "authors": authors,
        "provider": str(provider).strip(),
        "score": score,
    }


def score_results_relevance_llm(
    *,
    query: str,
    results: list[dict[str, Any]],
    min_score: float = 0.25,
    batch_size: int = 20,
) -> list[dict[str, Any]]:
    """LLM-based semantic relevance scoring — filters results below min_score.

    Processes in batches to stay within token limits.  Results that cannot be
    scored (LLM timeout, error) are passed through with a neutral score.
    """
    if not results:
        return results
    if not env_bool("MAIA_AGENT_LLM_RELEVANCE_SCORING_ENABLED", default=True):
        return results

    scored: list[dict[str, Any]] = []
    for batch_start in range(0, len(results), batch_size):
        batch = results[batch_start: batch_start + batch_size]
        candidates = [
            {
                "idx": j,
                "title": str(r.get("title") or "")[:120],
                "snippet": str(r.get("description") or "")[:200],
            }
            for j, r in enumerate(batch)
        ]
        payload = {"query": str(query or "")[:300], "candidates": candidates}
        response = call_json_response(
            system_prompt=(
                "You score web search results for query relevance for an enterprise research agent. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Score each candidate for semantic relevance to the query. Scale 0.0–1.0.\n"
                "Return JSON only:\n"
                '{ "scores": [{"idx": 0, "score": 0.85}] }\n'
                "Guide: 0.9+= directly answers query; 0.6–0.9= relevant context; "
                "0.3–0.6= loosely related; 0.0–0.3= off-topic.\n"
                "Judge by semantic relevance to query intent, not keyword matching.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=12,
            max_tokens=500,
        )
        if not isinstance(response, dict):
            scored.extend(batch)
            continue
        scores_raw = response.get("scores")
        if not isinstance(scores_raw, list):
            scored.extend(batch)
            continue
        score_map: dict[int, float] = {}
        for entry in scores_raw:
            if not isinstance(entry, dict):
                continue
            try:
                idx = int(entry.get("idx", -1))
                val = float(entry.get("score", 0.5))
                score_map[idx] = max(0.0, min(1.0, val))
            except Exception:
                pass
        for j, result in enumerate(batch):
            relevance = score_map.get(j, 0.5)
            if relevance >= min_score:
                r = dict(result)
                r["relevance_score"] = relevance
                scored.append(r)
    return scored


def safe_snippet(text: str, max_len: int = 280) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= max_len else f"{clean[: max_len - 1].rstrip()}..."


def clean_query(text: str) -> str:
    compact = " ".join(str(text or "").split())
    compact = re.sub(r"[^\w\s:/\.-]", " ", compact)
    compact = " ".join(compact.split())
    return compact.strip()


def extract_first_url(text: str) -> str:
    match = re.search(r"https?://[^\s]+", str(text or ""), re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).strip().rstrip(".,;)")


def normalize_search_provider(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"bing", "bing_search"}:
        return "bing_search"
    return "brave_search"


def truthy(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def extract_search_variants(
    query: str,
    prompt: str,
    *,
    requested_variants: list[str] | None = None,
    max_variants: int = 4,
) -> list[str]:
    variant_cap = max(1, min(int(max_variants or 4), 20))
    base = clean_query(query) or clean_query(prompt) or "web research request"
    url = extract_first_url(prompt) or extract_first_url(query)
    host = (urlparse(url).hostname or "").strip().lower() if url else ""
    host_no_www = host[4:] if host.startswith("www.") else host

    candidates: list[str] = [base]
    if isinstance(requested_variants, list):
        for row in requested_variants:
            text = clean_query(row)
            if text:
                candidates.append(text)
    if host_no_www:
        candidates.append(f"site:{host_no_www} {base}".strip())

    if env_bool("MAIA_AGENT_LLM_SEARCH_VARIANTS_ENABLED", default=True):
        payload = {
            "query": base,
            "request_prompt": " ".join(str(prompt or "").split())[:500],
            "target_url": url,
            "max_variants": variant_cap,
        }
        response = call_json_response(
            system_prompt=(
                "You generate diverse, high-signal search query variants for an enterprise research agent. "
                "Each variant should target a different retrieval angle so together they maximise recall across sources. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Generate diverse query variants for the search query below.\n"
                "Return JSON in this schema only:\n"
                '{ "query_variants": ["variant one", "variant two"] }\n'
                "Produce variants across these dimensions (pick the most relevant):\n"
                "- Temporal: add a year (e.g. '2024', '2025') or recency signal ('latest', 'recent', 'Q1 2025')\n"
                "- Aspect: focus on a specific facet — pricing, alternatives, competitors, risks, regulation, case studies, data\n"
                "- Competitive: frame as a comparison or ranking ('X vs Y', 'top providers of X', 'best alternatives to X')\n"
                "- Authoritative: add source signals like 'site:gov', 'filetype:pdf', 'research paper', 'annual report'\n"
                "- Rewrite: rephrase using domain synonyms or more precise technical terminology\n"
                "Rules:\n"
                "- Every variant must be grounded in the input — do not invent entities, names, or claims.\n"
                "- Keep each variant concise (under 15 words).\n"
                "- Do not repeat the original query verbatim.\n"
                f"- Return exactly 1-{variant_cap} variants.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=420,
        )
        normalized = sanitize_json_value(response) if isinstance(response, dict) else {}
        llm_rows = normalized.get("query_variants") if isinstance(normalized, dict) else []
        if isinstance(llm_rows, list):
            for row in llm_rows[:variant_cap]:
                text = clean_query(row)
                if text:
                    candidates.append(text)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        cleaned = clean_query(item)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
        if len(deduped) >= variant_cap:
            break
    return deduped or ["web research request"]


def fuse_search_results(
    search_runs: list[dict[str, Any]],
    *,
    top_k: int = 8,
    source_weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion across query rewrites and providers.

    Uses normalize_url_for_dedup() as the dedup key so that URLs differing
    only in tracking parameters (utm_*, fbclid, etc.) or http/https/www
    are treated as identical.  source_weights is an optional {domain: score}
    map that scales RRF scores by domain credibility.
    """
    k = 60.0
    # Maps normalized_url → canonical_url (first seen) + accumulated state
    by_norm_url: dict[str, dict[str, Any]] = {}
    for run in search_runs:
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for rank, row in enumerate(results, start=1):
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            norm_url = normalize_url_for_dedup(url)
            if not norm_url:
                norm_url = url
            title = str(row.get("title") or url).strip()
            description = str(row.get("description") or row.get("snippet") or "").strip()
            source = str(row.get("source") or "").strip()
            base_score = 1.0 / (k + float(rank))
            if source_weights:
                try:
                    domain = urlparse(url).netloc.lower()
                    if domain.startswith("www."):
                        domain = domain[4:]
                    weight = float(source_weights.get(domain, 0.62))
                    base_score = base_score * (0.5 + weight)
                except Exception:
                    pass
            current = by_norm_url.get(norm_url)
            if current is None:
                by_norm_url[norm_url] = {
                    "url": url,  # keep canonical (first seen) URL
                    "title": title,
                    "description": description,
                    "source": source or None,
                    "rrf_score": base_score,
                    "best_rank": rank,
                }
                continue
            current["rrf_score"] = float(current.get("rrf_score", 0.0)) + base_score
            if rank < int(current.get("best_rank", rank)):
                current["best_rank"] = rank
                current["title"] = title
                current["description"] = description
                current["source"] = source or None
    fused = list(by_norm_url.values())
    fused.sort(
        key=lambda item: (float(item.get("rrf_score", 0.0)), -int(item.get("best_rank", 9999))),
        reverse=True,
    )
    return fused[: max(1, int(top_k))]


def _domain_of(url: str) -> str:
    """Return the registered domain (no www, no port) for MMR similarity."""
    try:
        host = urlparse(str(url or "")).netloc.lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host.split(":")[0]


def mmr_rerank(
    results: list[dict[str, Any]],
    *,
    top_k: int,
    lambda_param: float = 0.7,
) -> list[dict[str, Any]]:
    """Maximal Marginal Relevance reranking for domain-level source diversity.

    Balances relevance (rrf_score) against redundancy (same domain already
    selected) so the final list spans multiple domains rather than clustering
    on whichever single domain ranked highest.

    lambda_param=0.7 → 70% relevance, 30% diversity.
    """
    if not results or top_k <= 0:
        return results[:top_k]
    if len(results) <= top_k:
        return results

    # Normalise rrf_scores to [0, 1] over the candidate set.
    scores = [float(r.get("rrf_score") or 0.0) for r in results]
    max_score = max(scores) if scores else 1.0
    if max_score == 0.0:
        max_score = 1.0
    norm_scores = [s / max_score for s in scores]

    lam = max(0.0, min(1.0, float(lambda_param)))
    selected_indices: list[int] = []
    selected_domains: list[str] = []
    remaining = list(range(len(results)))

    while len(selected_indices) < top_k and remaining:
        best_idx: int | None = None
        best_mmr: float = -1e9

        for i in remaining:
            relevance = norm_scores[i]
            candidate_domain = _domain_of(str(results[i].get("url") or ""))
            # Domain similarity: 1.0 if this domain is already selected, else 0.0.
            max_sim = 1.0 if candidate_domain and candidate_domain in selected_domains else 0.0
            mmr = lam * relevance - (1.0 - lam) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i

        if best_idx is None:
            break
        selected_indices.append(best_idx)
        selected_domains.append(_domain_of(str(results[best_idx].get("url") or "")))
        remaining.remove(best_idx)

    return [results[i] for i in selected_indices]


def classify_provider_failure(exc: Exception) -> dict[str, Any]:
    message = " ".join(str(exc or "").split()).strip()
    lowered = message.lower()
    status_code: int | None = None
    status_match = re.search(r"\((\d{3})\)", message)
    if status_match:
        try:
            status_code = int(status_match.group(1))
        except Exception:
            status_code = None

    if "not configured" in lowered or "api_key" in lowered:
        reason = "missing_credentials"
        retryable = False
    elif status_code in {401, 403} or "unauthorized" in lowered or "forbidden" in lowered:
        reason = "auth_error"
        retryable = False
    elif status_code == 429 or ("rate" in lowered and "limit" in lowered):
        reason = "rate_limited"
        retryable = True
    elif status_code in {500, 502, 503, 504}:
        reason = "upstream_error"
        retryable = True
    elif "timed out" in lowered or "timeout" in lowered:
        reason = "timeout"
        retryable = True
    elif "invalid payload" in lowered or "invalid json" in lowered:
        reason = "invalid_response"
        retryable = False
    else:
        reason = "provider_unavailable"
        retryable = False
    return {
        "reason": reason,
        "retryable": retryable,
        "status_code": status_code,
        "message": safe_snippet(message, 240),
    }


__all__ = [
    "classify_provider_failure",
    "clean_query",
    "extract_first_url",
    "extract_search_variants",
    "fuse_search_results",
    "mmr_rerank",
    "normalize_result_row",
    "normalize_search_provider",
    "normalize_url_for_dedup",
    "safe_snippet",
    "score_results_relevance_llm",
    "truthy",
]
