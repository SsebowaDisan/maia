from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value


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


def extract_search_variants(query: str, prompt: str) -> list[str]:
    base = clean_query(query) or clean_query(prompt) or "web research request"
    url = extract_first_url(prompt) or extract_first_url(query)
    host = (urlparse(url).hostname or "").strip().lower() if url else ""
    host_no_www = host[4:] if host.startswith("www.") else host

    candidates: list[str] = [base]
    if host_no_www:
        candidates.append(f"site:{host_no_www} {base}".strip())

    if env_bool("MAIA_AGENT_LLM_SEARCH_VARIANTS_ENABLED", default=True):
        payload = {
            "query": base,
            "request_prompt": " ".join(str(prompt or "").split())[:500],
            "target_url": url,
            "max_variants": 4,
        }
        response = call_json_response(
            system_prompt=(
                "You improve enterprise web-search query variants. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON in this schema only:\n"
                "{ \"query_variants\": [\"variant one\", \"variant two\"] }\n"
                "Rules:\n"
                "- Keep variants factual and grounded in input.\n"
                "- Do not invent company names, URLs, or facts.\n"
                "- Return 1-4 concise variants.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=220,
        )
        normalized = sanitize_json_value(response) if isinstance(response, dict) else {}
        llm_rows = normalized.get("query_variants") if isinstance(normalized, dict) else []
        if isinstance(llm_rows, list):
            for row in llm_rows[:4]:
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
        if len(deduped) >= 4:
            break
    return deduped or ["web research request"]


def fuse_search_results(search_runs: list[dict[str, Any]], *, top_k: int = 8) -> list[dict[str, Any]]:
    # Reciprocal Rank Fusion (RRF): robust ranking across query rewrites.
    k = 60.0
    by_url: dict[str, dict[str, Any]] = {}
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
            title = str(row.get("title") or url).strip()
            description = str(row.get("description") or "").strip()
            source = str(row.get("source") or "").strip()
            score = 1.0 / (k + float(rank))
            current = by_url.get(url)
            if current is None:
                by_url[url] = {
                    "url": url,
                    "title": title,
                    "description": description,
                    "source": source or None,
                    "rrf_score": score,
                    "best_rank": rank,
                }
                continue
            current["rrf_score"] = float(current.get("rrf_score", 0.0)) + score
            if rank < int(current.get("best_rank", rank)):
                current["best_rank"] = rank
                current["title"] = title
                current["description"] = description
                current["source"] = source or None
    fused = list(by_url.values())
    fused.sort(
        key=lambda item: (float(item.get("rrf_score", 0.0)), -int(item.get("best_rank", 9999))),
        reverse=True,
    )
    return fused[: max(1, int(top_k))]


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
    "normalize_search_provider",
    "safe_snippet",
    "truthy",
]
