from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


def _extract_url(message: str, goal: str) -> str:
    combined = f"{message} {goal}".strip()
    match = re.search(r"https?://[^\s]+", combined, flags=re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _host_tokens(url: str) -> list[str]:
    host = (urlparse(url).hostname or "").strip().lower()
    if not host:
        return []
    host = host.replace("www.", "")
    pieces = [piece for piece in re.split(r"[^a-z0-9]+", host) if piece and piece not in {"com", "org", "net"}]
    return pieces[:3]


def _extract_candidate_keywords(message: str, goal: str, *, url: str = "") -> list[str]:
    tokens = [match.group(0).lower() for match in WORD_RE.finditer(f"{message} {goal}")]
    deduped = list(dict.fromkeys(tokens))
    for host_token in _host_tokens(url):
        if host_token not in deduped:
            deduped.insert(0, host_token)
    return deduped[:48]


def _seed_keywords(message: str, goal: str, *, min_keywords: int, url: str = "") -> list[str]:
    deduped = _extract_candidate_keywords(message, goal, url=url)
    if len(deduped) >= min_keywords:
        return deduped[: max(min_keywords, 16)]
    if not deduped:
        host_parts = _host_tokens(url)
        deduped.extend(host_parts or ["request"])
    base = deduped[0]
    while len(deduped) < min_keywords:
        candidate = f"{base}_{len(deduped) + 1}"
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped[: max(min_keywords, 16)]


def _heuristic_search_terms(
    message: str,
    goal: str,
    keywords: list[str],
    *,
    url: str = "",
) -> list[str]:
    host = (urlparse(url).hostname or "").strip().lower()
    terms: list[str] = []
    compact_message = " ".join(f"{message} {goal}".split()).strip()
    if host:
        if compact_message:
            terms.append(f"site:{host} {compact_message[:120]}")
        terms.append(f"site:{host}")
    if keywords:
        terms.append(" ".join(keywords[:4]))
        if len(keywords) >= 8:
            terms.append(" ".join(keywords[4:8]))
    if compact_message:
        terms.append(compact_message[:160])
    deduped = [item for item in dict.fromkeys(item.strip() for item in terms if item.strip())]
    return deduped[:6]


def _normalize_keywords(raw: Any, *, min_keywords: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    cleaned = []
    for item in raw:
        text = " ".join(str(item or "").split()).strip().lower()
        if len(text) < 2:
            continue
        cleaned.append(text[:80])
    deduped = list(dict.fromkeys(cleaned))
    return deduped[: max(min_keywords, 24)]


def _normalize_terms(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    cleaned = []
    for item in raw:
        text = " ".join(str(item or "").split()).strip()
        if not text:
            continue
        cleaned.append(text[:180])
    return list(dict.fromkeys(cleaned))[:8]


def _request_blueprint_with_llm(*, message: str, goal: str, url: str, min_keywords: int) -> dict[str, Any] | None:
    payload = {
        "message": message,
        "agent_goal": goal,
        "url": url,
        "min_keywords": min_keywords,
    }
    prompt = (
        "Produce a research blueprint for an enterprise agent.\n"
        "Return JSON only in this schema:\n"
        "{\n"
        '  "search_terms": ["term 1", "term 2"],\n'
        '  "keywords": ["keyword 1", "keyword 2"],\n'
        '  "rationale": "one short sentence"\n'
        "}\n"
        "Rules:\n"
        "- keywords must contain at least min_keywords unique items.\n"
        "- search_terms should be executable web queries.\n"
        "- No markdown.\n"
        "- Keep each keyword concise.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    return call_json_response(
        system_prompt=(
            "You are a precise research planner for business intelligence tasks. "
            "Return strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=14,
        max_tokens=900,
    )


def build_research_blueprint(
    *,
    message: str,
    agent_goal: str | None,
    min_keywords: int = 10,
) -> dict[str, Any]:
    target_min = max(10, int(min_keywords or 10))
    clean_message = str(message or "").strip()
    clean_goal = str(agent_goal or "").strip()
    target_url = _extract_url(clean_message, clean_goal)

    keywords = _seed_keywords(
        clean_message,
        clean_goal,
        min_keywords=target_min,
        url=target_url,
    )
    search_terms = _heuristic_search_terms(
        clean_message,
        clean_goal,
        keywords,
        url=target_url,
    )
    rationale = "Generated fallback research blueprint from request context."

    if env_bool("MAIA_AGENT_LLM_RESEARCH_BLUEPRINT_ENABLED", default=True):
        payload = _request_blueprint_with_llm(
            message=clean_message,
            goal=clean_goal,
            url=target_url,
            min_keywords=target_min,
        )
        if isinstance(payload, dict):
            normalized = sanitize_json_value(payload)
            if isinstance(normalized, dict):
                candidate_keywords = _normalize_keywords(normalized.get("keywords"), min_keywords=target_min)
                candidate_terms = _normalize_terms(normalized.get("search_terms"))
                candidate_rationale = " ".join(str(normalized.get("rationale") or "").split()).strip()
                if candidate_keywords:
                    keywords = candidate_keywords
                if candidate_terms:
                    search_terms = candidate_terms
                if candidate_rationale:
                    rationale = candidate_rationale[:220]

    if len(keywords) < target_min:
        refill = _seed_keywords(
            clean_message,
            clean_goal,
            min_keywords=target_min,
            url=target_url,
        )
        for item in refill:
            if item not in keywords:
                keywords.append(item)
            if len(keywords) >= target_min:
                break
    if len(search_terms) < 2:
        fallback_terms = _heuristic_search_terms(
            clean_message,
            clean_goal,
            keywords,
            url=target_url,
        )
        for term in fallback_terms:
            if term not in search_terms:
                search_terms.append(term)
            if len(search_terms) >= 4:
                break

    return {
        "search_terms": search_terms[:6],
        "keywords": keywords[: max(target_min, 16)],
        "rationale": rationale,
        "target_url": target_url,
    }
