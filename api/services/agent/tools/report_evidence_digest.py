from __future__ import annotations

import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool


YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _source_year(row: dict[str, Any]) -> int | None:
    text = " ".join(
        str(item or "").strip()
        for item in (
            row.get("label"),
            row.get("url"),
            row.get("snippet"),
        )
        if str(item or "").strip()
    )
    years = [int(match.group(1)) for match in YEAR_RE.finditer(text)]
    if not years:
        return None
    return min(years)


def _source_era_label(row: dict[str, Any]) -> str:
    year = _source_year(row)
    if year is None:
        return "validation: year not explicit"
    if year <= 2005:
        return f"foundational: {year}"
    return f"validation: {year}"


def _fallback_evidence_findings(
    source_rows: list[dict[str, str]],
    *,
    max_findings: int,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for idx, row in enumerate(source_rows[: max(3, max_findings * 2)], start=1):
        label = " ".join(str(row.get("label") or "").split()).strip() or f"Source {idx}"
        snippet = " ".join(str(row.get("snippet") or "").split()).strip()
        if not snippet:
            continue
        findings.append(
            {
                "heading": label[:90],
                "insight": snippet[:420],
                "plain_language_explanation": (
                    f"This matters because it anchors the brief in a named source instead of an unsupported summary, "
                    f"with source era labeled as {_source_era_label(row)}."
                )[:320],
                "source_indices": [idx],
            }
        )
        if len(findings) >= max_findings:
            break
    return findings


def _build_evidence_findings_with_llm(
    *,
    title: str,
    prompt: str,
    source_rows: list[dict[str, str]],
    depth_tier: str,
    required_facts: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not env_bool("MAIA_AGENT_LLM_REPORT_EVIDENCE_DIGEST_ENABLED", default=True):
        return []
    if not source_rows:
        return []

    numbered_sources = [
        {
            "index": i + 1,
            "label": " ".join(str(row.get("label") or "").split()).strip()[:180],
            "url": " ".join(str(row.get("url") or "").split()).strip()[:260],
            "snippet": " ".join(str(row.get("snippet") or "").split()).strip()[:280],
        }
        for i, row in enumerate(source_rows[:36])
        if " ".join(str(row.get("label") or row.get("snippet") or "").split()).strip()
    ]
    if len(numbered_sources) < 3:
        return []

    max_findings = 6 if depth_tier in {"deep_research", "deep_analytics", "expert"} else 4
    payload = {
        "title": " ".join(str(title or "").split()).strip()[:220],
        "prompt": " ".join(str(prompt or "").split()).strip()[:700],
        "depth_tier": " ".join(str(depth_tier or "").split()).strip().lower() or "standard",
        "required_facts": [
            " ".join(str(item or "").split()).strip()[:220]
            for item in list(required_facts or [])[:6]
            if " ".join(str(item or "").split()).strip()
        ],
        "sources": numbered_sources,
    }
    response = call_json_response(
        system_prompt=(
            "You distill evidence-backed research findings for executive briefs. "
            "Return strict JSON only. Every finding must be grounded in the provided numbered sources."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "findings": ['
            '{ "heading": "string", "insight": "string", "plain_language_explanation": "string", "source_indices": [1,2] }'
            "] }\n"
            "Rules:\n"
            f"- Provide 3-{max_findings} findings.\n"
            "- Cover the required_facts first whenever the evidence supports them.\n"
            "- Each insight must state one clear, evidence-backed point.\n"
            "- Each plain_language_explanation must explain why the point matters in simple, direct language.\n"
            "- Use only the numbered sources provided.\n"
            "- source_indices must reference the strongest 1-3 supporting sources.\n"
            "- Do not invent claims, URLs, or statistics.\n"
            "- Avoid filler, meta commentary, and generic acknowledgements.\n"
            "- Prefer concise, high-signal wording suitable for an executive research brief.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.15,
        timeout_seconds=18,
        max_tokens=1800,
    )
    raw = response.get("findings") if isinstance(response, dict) else None
    if not isinstance(raw, list):
        return []

    cleaned: list[dict[str, Any]] = []
    max_index = len(numbered_sources)
    for item in raw[:max_findings]:
        if not isinstance(item, dict):
            continue
        heading = " ".join(str(item.get("heading") or "").split()).strip()[:90]
        insight = " ".join(str(item.get("insight") or "").split()).strip()[:420]
        explanation = " ".join(
            str(item.get("plain_language_explanation") or "").split()
        ).strip()[:320]
        source_indices_raw = item.get("source_indices")
        source_indices: list[int] = []
        if isinstance(source_indices_raw, list):
            for value in source_indices_raw[:3]:
                try:
                    idx = int(value)
                except Exception:
                    continue
                if 1 <= idx <= max_index and idx not in source_indices:
                    source_indices.append(idx)
        if heading and insight and explanation and source_indices:
            cleaned.append(
                {
                    "heading": heading,
                    "insight": insight,
                    "plain_language_explanation": explanation,
                    "source_indices": source_indices,
                }
            )
    fallback = _fallback_evidence_findings(source_rows, max_findings=max_findings)
    if len(cleaned) >= min(3, max_findings):
        return cleaned[:max_findings]
    seen_indices = {
        tuple(item.get("source_indices") or [])
        for item in cleaned
        if isinstance(item, dict)
    }
    for item in fallback:
        key = tuple(item.get("source_indices") or [])
        if key in seen_indices:
            continue
        cleaned.append(item)
        seen_indices.add(key)
        if len(cleaned) >= max_findings:
            break
    return cleaned[:max_findings]


def _evidence_findings_markdown(
    findings: list[dict[str, Any]],
    source_rows: list[dict[str, str]],
) -> str:
    if not findings:
        return ""
    lines: list[str] = ["### Evidence-backed findings", ""]
    for finding in findings:
        heading = " ".join(str(finding.get("heading") or "").split()).strip()
        insight = " ".join(str(finding.get("insight") or "").split()).strip()
        explanation = " ".join(
            str(finding.get("plain_language_explanation") or "").split()
        ).strip()
        indices = finding.get("source_indices")
        evidence_links: list[str] = []
        if isinstance(indices, list):
            for value in indices[:3]:
                try:
                    idx = int(value)
                except Exception:
                    continue
                if idx < 1 or idx > len(source_rows):
                    continue
                row = source_rows[idx - 1]
                label = " ".join(str(row.get("label") or "").split()).strip() or f"Source {idx}"
                url = " ".join(str(row.get("url") or "").split()).strip()
                if url:
                    evidence_links.append(f"[{label}]({url})")
                else:
                    evidence_links.append(label)
        if heading:
            lines.append(f"#### {heading}")
        lines.append(f"- Insight: {insight}")
        lines.append(f"- Why it matters: {explanation}")
        if evidence_links:
            lines.append(f"- Evidence: {'; '.join(evidence_links)}")
        if isinstance(indices, list) and indices:
            row = source_rows[int(indices[0]) - 1]
            lines.append(f"- Source era: {_source_era_label(row)}")
        lines.append("")
    return "\n".join(lines).strip()


def _annotated_source_lines(
    source_rows: list[dict[str, str]],
    *,
    limit: int = 7,
) -> list[str]:
    lines: list[str] = []
    for row in source_rows[: max(1, int(limit))]:
        label = " ".join(str(row.get("label") or "").split()).strip() or "Source"
        url = " ".join(str(row.get("url") or "").split()).strip()
        snippet = " ".join(str(row.get("snippet") or "").split()).strip()
        if url and snippet:
            lines.append(f"- [{label}]({url}) — {snippet}")
        elif url:
            lines.append(f"- [{label}]({url})")
        elif snippet:
            lines.append(f"- {label} — {snippet}")
        else:
            lines.append(f"- {label}")
    return lines
