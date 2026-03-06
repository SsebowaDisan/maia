from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
PLACEHOLDER_KEYWORD_RE = re.compile(r"^([a-z][a-z0-9-]*)_([0-9]{1,3})$")
MAX_SEARCH_TERMS = 24


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
    tokens = [
        match.group(0).lower()
        for match in WORD_RE.finditer(f"{message} {goal}")
        if len(match.group(0)) >= 3
    ]
    deduped = list(dict.fromkeys(tokens))
    for host_token in _host_tokens(url):
        if host_token not in deduped:
            deduped.insert(0, host_token)
    return deduped[:48]


def _seed_keywords(message: str, goal: str, *, min_keywords: int, url: str = "") -> list[str]:
    target = max(4, int(min_keywords or 4))
    deduped = _extract_candidate_keywords(message, goal, url=url)
    if not deduped:
        host_parts = _host_tokens(url)
        deduped.extend(host_parts or ["research"])
    return deduped[: max(target, 16)]


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
    for start in range(0, min(len(keywords), 24), 3):
        chunk = " ".join(keywords[start : start + 4]).strip()
        if chunk:
            terms.append(chunk)
    deduped = [item for item in dict.fromkeys(item.strip() for item in terms if item.strip())]
    return deduped[:MAX_SEARCH_TERMS]


def _llm_only_fallback_search_terms(
    *,
    message: str,
    goal: str,
    keywords: list[str],
    url: str = "",
) -> list[str]:
    terms: list[str] = []
    compact_message = " ".join(f"{message} {goal}".split()).strip()
    host = (urlparse(url).hostname or "").strip().lower()
    if compact_message:
        terms.append(compact_message[:160])
    if host:
        if compact_message:
            terms.append(f"site:{host} {compact_message[:120]}")
        else:
            terms.append(f"site:{host}")
    if keywords:
        terms.append(" ".join(keywords[:4]))
        for start in range(4, min(len(keywords), 24), 3):
            chunk = " ".join(keywords[start : start + 4]).strip()
            if chunk:
                terms.append(chunk)
    deduped = [item for item in dict.fromkeys(item.strip() for item in terms if item.strip())]
    return deduped[:MAX_SEARCH_TERMS]


def _normalize_keywords(raw: Any, *, min_keywords: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    cleaned = []
    seen: set[str] = set()
    for item in raw:
        text = " ".join(str(item or "").split()).strip().lower()
        if len(text) < 2:
            continue
        text = text[:80]
        placeholder_match = PLACEHOLDER_KEYWORD_RE.match(text)
        if placeholder_match:
            base = placeholder_match.group(1)
            if base in seen:
                continue
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    deduped = cleaned
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
    return list(dict.fromkeys(cleaned))[:MAX_SEARCH_TERMS]


def _request_blueprint_with_llm(
    *,
    message: str,
    goal: str,
    url: str,
    min_keywords: int,
    min_search_terms: int,
) -> dict[str, Any] | None:
    payload = {
        "message": message,
        "agent_goal": goal,
        "url": url,
        "min_keywords": min_keywords,
        "min_search_terms": min_search_terms,
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
        "- Aim for at least min_keywords unique items when it adds real value.\n"
        "- Aim for at least min_search_terms distinct executable search_terms.\n"
        "- search_terms should be executable web queries.\n"
        "- No markdown.\n"
        "- Keep each keyword concise.\n\n"
        "- Never fabricate placeholder keywords like 'term_4' or repeated numbering.\n\n"
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


def _expand_search_terms_with_llm(
    *,
    message: str,
    goal: str,
    url: str,
    existing_terms: list[str],
    min_search_terms: int,
) -> list[str]:
    if len(existing_terms) >= min_search_terms:
        return []
    payload = {
        "message": message,
        "agent_goal": goal,
        "url": url,
        "existing_search_terms": existing_terms[:MAX_SEARCH_TERMS],
        "min_search_terms": min_search_terms,
    }
    response = call_json_response(
        system_prompt=(
            "You expand enterprise web-search plans. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "search_terms": ["query 1", "query 2"] }\n'
            "Rules:\n"
            "- Expand breadth across subtopics, perspectives, and source types.\n"
            "- Do not duplicate existing_search_terms.\n"
            "- Keep each query concise and directly executable.\n"
            f"- Return enough terms to reach at least {min_search_terms} total terms when merged.\n\n"
            f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
        ),
        temperature=0.0,
        timeout_seconds=10,
        max_tokens=620,
    )
    if not isinstance(response, dict):
        return []
    normalized = sanitize_json_value(response)
    if not isinstance(normalized, dict):
        return []
    candidate_terms = _normalize_terms(normalized.get("search_terms"))
    if not candidate_terms:
        return []
    existing_norm = {
        " ".join(str(item).split()).strip().lower()
        for item in existing_terms
        if " ".join(str(item).split()).strip()
    }
    expanded: list[str] = []
    for term in candidate_terms:
        key = " ".join(str(term).split()).strip().lower()
        if not key or key in existing_norm:
            continue
        expanded.append(term)
        existing_norm.add(key)
        if len(expanded) >= max(2, min_search_terms):
            break
    return expanded


def build_research_blueprint(
    *,
    message: str,
    agent_goal: str | None,
    min_keywords: int = 10,
    min_search_terms: int = 4,
    llm_only: bool = True,
    llm_strict: bool = False,
) -> dict[str, Any]:
    target_min = max(10, int(min_keywords or 10))
    target_search_terms = max(2, min(int(min_search_terms or 2), 20))
    clean_message = str(message or "").strip()
    clean_goal = str(agent_goal or "").strip()
    target_url = _extract_url(clean_message, clean_goal)

    if llm_only:
        keywords: list[str] = []
        search_terms: list[str] = []
        rationale = "Generated from LLM research blueprint."
    else:
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
            min_search_terms=target_search_terms,
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
        if len(search_terms) < target_search_terms:
            expanded_terms = _expand_search_terms_with_llm(
                message=clean_message,
                goal=clean_goal,
                url=target_url,
                existing_terms=search_terms,
                min_search_terms=target_search_terms,
            )
            for term in expanded_terms:
                if term not in search_terms:
                    search_terms.append(term)
                if len(search_terms) >= target_search_terms:
                    break

    if llm_only:
        if len(keywords) < 4:
            if llm_strict:
                return {
                    "search_terms": search_terms[:MAX_SEARCH_TERMS],
                    "keywords": keywords[: max(target_min, 16)],
                    "rationale": rationale,
                    "target_url": target_url,
                }
            fallback_keywords = _extract_candidate_keywords(
                clean_message,
                clean_goal,
                url=target_url,
            )
            for item in fallback_keywords:
                if item not in keywords:
                    keywords.append(item)
                if len(keywords) >= max(target_min, 16):
                    break
        if len(search_terms) < target_search_terms:
            if llm_strict:
                return {
                    "search_terms": search_terms[:MAX_SEARCH_TERMS],
                    "keywords": keywords[: max(target_min, 16)],
                    "rationale": rationale,
                    "target_url": target_url,
                }
            fallback_terms = _llm_only_fallback_search_terms(
                message=clean_message,
                goal=clean_goal,
                keywords=keywords,
                url=target_url,
            )
            for term in fallback_terms:
                if term not in search_terms:
                    search_terms.append(term)
                if len(search_terms) >= target_search_terms:
                    break
    else:
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
        if len(search_terms) < target_search_terms:
            fallback_terms = _heuristic_search_terms(
                clean_message,
                clean_goal,
                keywords,
                url=target_url,
            )
            for term in fallback_terms:
                if term not in search_terms:
                    search_terms.append(term)
                if len(search_terms) >= target_search_terms:
                    break

    return {
        "search_terms": search_terms[:MAX_SEARCH_TERMS],
        "keywords": keywords[: max(target_min, 16)],
        "rationale": rationale,
        "target_url": target_url,
    }
