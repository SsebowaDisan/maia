from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value


def _normalize_url_list(raw_urls: Any, *, limit: int = 5) -> list[str]:
    if not isinstance(raw_urls, list):
        return []
    urls: list[str] = []
    for item in raw_urls:
        value = str(item or "").strip()
        if not value:
            continue
        if not (value.startswith("http://") or value.startswith("https://")):
            continue
        if value in urls:
            continue
        urls.append(value)
        if len(urls) >= max(1, int(limit)):
            break
    return urls


def build_location_delivery_brief(
    *,
    request_message: str,
    objective: str,
    report_body: str,
    browser_findings: dict[str, Any] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a fact-grounded brief via LLM (no keyword heuristics)."""
    if not env_bool("MAIA_AGENT_LLM_LOCATION_BRIEF_ENABLED", default=True):
        return {"summary": "", "address": "", "evidence_urls": [], "confidence": "unknown"}
    payload = {
        "request_message": " ".join(str(request_message or "").split()).strip()[:480],
        "objective": " ".join(str(objective or "").split()).strip()[:480],
        "report_body": str(report_body or "").strip()[:1800],
        "browser_findings": sanitize_json_value(browser_findings or {}),
        "sources": sanitize_json_value(sources or []),
    }
    prompt = (
        "Synthesize a location answer from task evidence for an outbound email.\n"
        "Return JSON only:\n"
        '{ "summary": "string", "address": "string", "evidence_urls": ["..."], "confidence": "high|medium|low|unknown" }\n'
        "Rules:\n"
        "- Use only evidence from input payload.\n"
        "- `summary` must state where the company is found or state that evidence is insufficient.\n"
        "- `address` should be empty if not explicitly present in evidence.\n"
        "- Include up to 5 relevant evidence URLs.\n"
        "- Do not invent data.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You extract location findings from evidence for enterprise reporting. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=320,
    )
    if not isinstance(response, dict):
        return {"summary": "", "address": "", "evidence_urls": [], "confidence": "unknown"}

    summary = " ".join(str(response.get("summary") or "").split()).strip()[:420]
    address = " ".join(str(response.get("address") or "").split()).strip()[:260]
    confidence_raw = str(response.get("confidence") or "").strip().lower()
    confidence = (
        confidence_raw
        if confidence_raw in {"high", "medium", "low", "unknown"}
        else "unknown"
    )
    urls = _normalize_url_list(response.get("evidence_urls"), limit=5)

    if not urls and isinstance(sources, list):
        urls = _normalize_url_list(
            [row.get("url") for row in sources if isinstance(row, dict)],
            limit=5,
        )
    return {
        "summary": summary,
        "address": address,
        "evidence_urls": urls,
        "confidence": confidence,
    }
