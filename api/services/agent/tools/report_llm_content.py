from __future__ import annotations

import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, call_text_response, env_bool
from api.services.agent.tools.report_utils import (
    REQUEST_STYLE_RE,
    _theme_examples,
    _topic_label,
    _top_terms_from_sources,
)

EMAIL_DRAFT_HEADING_RE = re.compile(r"(?im)^\s*(?:#{1,6}\s*)?email\s*draft\s*:?\s*$")
PLACEHOLDER_SIGNATURE_RE = re.compile(
    r"(?im)^\s*\[(?:your name|your position|your contact information)\]\s*$"
)


def _sanitize_report_markdown_output(text: str) -> str:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return ""
    lines: list[str] = []
    for line in raw.splitlines():
        if EMAIL_DRAFT_HEADING_RE.match(str(line or "").strip()):
            break
        if PLACEHOLDER_SIGNATURE_RE.match(str(line or "").strip()):
            continue
        lines.append(str(line or "").rstrip())
    clean = "\n".join(lines).strip()
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


def _compose_executive_summary(
    *,
    title: str,
    summary: str,
    prompt: str,
    source_rows: list[dict[str, str]],
    depth_tier: str,
) -> str:
    clean_summary = " ".join(str(summary or "").split()).strip()
    topic = _topic_label(title=title, prompt=prompt, summary=clean_summary)
    source_count = len(source_rows)
    needs_enrichment = (
        not clean_summary
        or len(clean_summary) < 140
        or REQUEST_STYLE_RE.match(clean_summary) is not None
        or clean_summary.lower() in {"no summary provided.", "no summary provided"}
    )
    if source_count <= 0 and clean_summary and REQUEST_STYLE_RE.match(clean_summary) is None and len(clean_summary) >= 60:
        return clean_summary
    if source_count <= 0 and not needs_enrichment:
        return clean_summary

    top_terms = _top_terms_from_sources(source_rows, limit=6) if source_rows else []
    terms_text = ", ".join(top_terms[:5]) if top_terms else ""
    coverage_sentence = (
        f"This synthesis is grounded in {source_count} captured source(s), with emphasis on evidence quality and cross-source consistency."
        if source_count > 0
        else "This synthesis is based on the currently captured evidence and execution trace."
    )
    trend_sentence = (
        f"Recurring themes include {terms_text}, indicating where technical momentum and practical adoption are currently concentrated."
        if terms_text
        else "Key themes were extracted from available sources to map what is mature, emerging, and still uncertain."
    )
    implication_sentence = (
        "For decision-makers, the priority is balancing capability gains (quality, speed, automation) against reliability, governance, and operational cost."
    )
    gap_sentence = (
        "Areas with weaker evidence are called out as data gaps and should be validated with additional primary or peer-reviewed sources before high-stakes use."
    )

    if needs_enrichment:
        paragraphs = [
            f"This report provides a deep research synthesis on {topic}, focusing on technical advances, practical impact, and decision-relevant trade-offs.",
            coverage_sentence,
            trend_sentence,
            implication_sentence,
        ]
    else:
        paragraphs = [clean_summary, coverage_sentence, trend_sentence]
        if depth_tier in {"deep_research", "deep_analytics", "expert"}:
            paragraphs.append(implication_sentence)

    if depth_tier in {"deep_research", "deep_analytics", "expert"}:
        paragraphs.append(gap_sentence)

    return "\n\n".join(paragraphs)


def _analysis_paragraphs_with_llm(
    *,
    title: str,
    summary: str,
    prompt: str,
    source_rows: list[dict[str, str]],
    depth_tier: str,
) -> list[str]:
    if not env_bool("MAIA_AGENT_LLM_REPORT_ANALYSIS_ENABLED", default=True):
        return []
    deep_mode = depth_tier in {"deep_research", "deep_analytics", "expert"}
    min_paragraphs = 8 if deep_mode else 4
    max_paragraphs = 36 if deep_mode else 16
    source_slice = source_rows[:48] if deep_mode else source_rows[:20]

    numbered_sources = [
        f"[{i + 1}] {str(row.get('label') or '').strip()}: {str(row.get('snippet') or '').strip()[:200]}"
        for i, row in enumerate(source_slice)
        if str(row.get("label") or row.get("snippet") or "").strip()
    ]
    payload = {
        "title": " ".join(str(title or "").split()).strip()[:220],
        "summary": " ".join(str(summary or "").split()).strip()[:1200],
        "prompt": " ".join(str(prompt or "").split()).strip()[:520],
        "depth_tier": depth_tier,
        "sources": numbered_sources,
    }
    response = call_json_response(
        system_prompt=(
            "Write professional, evidence-grounded analysis paragraphs for executive research reports. "
            "Cite specific sources inline using [n] notation where n matches the numbered source list. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "analysis_paragraphs": ["paragraph with [1] citation.", "paragraph with [2][3] citations."] }\n'
            "Rules:\n"
            f"- Provide {min_paragraphs}-{max_paragraphs} substantive paragraphs.\n"
            "- Cover mechanisms, evidence patterns, trade-offs, and practical implications.\n"
            "- Cite sources inline using [n] immediately after the claim they support — only when the source genuinely backs the claim.\n"
            "- Multiple citations on one sentence are allowed: [1][3].\n"
            "- If no source supports a claim, write it without a citation rather than guessing.\n"
            "- Use only provided context; do not fabricate facts or URLs.\n"
            "- Keep each paragraph between 1-4 sentences.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.2,
        timeout_seconds=18,
        max_tokens=3200,
    )
    rows = response.get("analysis_paragraphs") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        return []
    cleaned: list[str] = []
    for item in rows[:max_paragraphs]:
        line = " ".join(str(item or "").split()).strip()
        if not line:
            continue
        cleaned.append(line[:1400])
    if deep_mode:
        total_chars = sum(len(item) for item in cleaned)
        if len(cleaned) < min_paragraphs or total_chars < 2200:
            return []
    return cleaned


def _fallback_analysis_paragraphs(
    *,
    summary: str,
    prompt: str,
    title: str,
    source_rows: list[dict[str, str]],
    depth_tier: str,
) -> list[str]:
    topic = _topic_label(title=title, prompt=prompt, summary=summary)
    source_count = len(source_rows)
    if source_count <= 0:
        return [
            (
                f"This report addresses {topic} and presents the strongest currently available findings, "
                "while keeping assumptions explicit."
            ),
            (
                "Because source coverage is limited, conclusions should be treated as directional until additional "
                "primary evidence is collected and cross-validated."
            ),
            "Prioritize independent verification for any decision with legal, financial, or safety impact.",
        ]

    theme_rows = _theme_examples(source_rows)
    paragraphs: list[str] = [
        (
            f"The analysis synthesizes {source_count} source-backed signal(s) on {topic}, focusing on where evidence converges, "
            "where it diverges, and what that means for practical execution."
        )
    ]
    for theme_name, snippets in theme_rows[:3]:
        examples = "; ".join(snippets[:2])
        paragraphs.append(
            (
                f"{theme_name}: evidence repeatedly points to this area as a central driver of current progress. "
                f"Representative findings include {examples}. "
                "Taken together, this suggests both technical opportunity and operational complexity that must be managed explicitly."
            )
        )
    top_terms = _top_terms_from_sources(source_rows, limit=6)
    if top_terms:
        paragraphs.append(
            (
                f"Across sources, the most recurrent terms ({', '.join(top_terms[:5])}) indicate that momentum is concentrated in a few high-impact domains, "
                "which helps prioritize where to invest research and implementation effort first."
            )
        )
    paragraphs.append(
        "From an execution standpoint, the strongest near-term value comes from targeted pilot deployments, "
        "clear evaluation criteria, and continuous monitoring for reliability drift."
    )
    paragraphs.append(
        "Risk posture should account for data quality, reproducibility, model behavior under distribution shift, "
        "and governance requirements before scaling to customer-facing or regulated workflows."
    )
    if depth_tier in {"deep_research", "deep_analytics", "expert"}:
        paragraphs.append(
            "Recommended follow-up is to expand primary-source coverage on unresolved claims, quantify performance/cost trade-offs, "
            "and maintain a living evidence log that can support auditability."
        )
    return paragraphs[:10]


def _detect_source_contradictions(
    source_rows: list[dict[str, str]],
    *,
    topic: str,
) -> list[dict[str, str]]:
    if not env_bool("MAIA_AGENT_LLM_CONTRADICTION_DETECTION_ENABLED", default=True):
        return []
    if len(source_rows) < 4:
        return []
    source_summaries = [
        f"[{i + 1}] {str(row.get('label') or '').strip()}: {str(row.get('snippet') or '').strip()[:220]}"
        for i, row in enumerate(source_rows[:14])
        if str(row.get("label") or row.get("snippet") or "").strip()
    ]
    if len(source_summaries) < 4:
        return []
    payload = {
        "topic": " ".join(str(topic or "").split()).strip()[:280],
        "sources": source_summaries,
    }
    response = call_json_response(
        system_prompt=(
            "You identify factual contradictions between research sources for enterprise intelligence reports. "
            "Only flag genuine, specific conflicts — not differences in emphasis. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Review the numbered sources below and identify any pairs that directly contradict each other "
            "on a specific, verifiable fact (e.g. revenue figures, market share %, headcount, a date, a product spec).\n"
            "Return JSON only in this schema:\n"
            '{ "contradictions": [\n'
            '    { "conflict_topic": "string", "claim_a": "string", "source_a": "string", "claim_b": "string", "source_b": "string" }\n'
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- Only report conflicts where two sources state clearly different values for the SAME fact.\n"
            "- Do NOT flag differences in opinion, framing, or emphasis — only hard factual conflicts.\n"
            "- Keep claim_a and claim_b under 160 characters each.\n"
            "- source_a and source_b must be the label of the relevant source (from the numbered list).\n"
            "- Return an empty contradictions list if no genuine conflicts exist.\n"
            "- Maximum 5 contradictions.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=600,
    )
    if not isinstance(response, dict):
        return []
    raw = response.get("contradictions")
    if not isinstance(raw, list):
        return []
    conflicts: list[dict[str, str]] = []
    for item in raw[:5]:
        if not isinstance(item, dict):
            continue
        conflict_topic = " ".join(str(item.get("conflict_topic") or "").split()).strip()[:160]
        claim_a = " ".join(str(item.get("claim_a") or "").split()).strip()[:200]
        source_a = " ".join(str(item.get("source_a") or "").split()).strip()[:120]
        claim_b = " ".join(str(item.get("claim_b") or "").split()).strip()[:200]
        source_b = " ".join(str(item.get("source_b") or "").split()).strip()[:120]
        if claim_a and claim_b and source_a and source_b:
            conflicts.append(
                {
                    "conflict_topic": conflict_topic,
                    "claim_a": claim_a,
                    "source_a": source_a,
                    "claim_b": claim_b,
                    "source_b": source_b,
                }
            )
    return conflicts


def _contradiction_section_lines(conflicts: list[dict[str, str]]) -> list[str]:
    if not conflicts:
        return []
    lines: list[str] = [
        "### Source Conflicts",
        "",
        "> The following factual discrepancies were detected across sources. "
        "Verify independently before drawing conclusions.",
        "",
    ]
    for i, c in enumerate(conflicts, start=1):
        topic = c.get("conflict_topic") or "Conflicting claim"
        lines.append(f"**Conflict {i}: {topic}**")
        lines.append(f"- {c.get('source_a', 'Source A')}: {c.get('claim_a', '')}")
        lines.append(f"- {c.get('source_b', 'Source B')}: {c.get('claim_b', '')}")
        lines.append("")
    return lines


def _recommended_next_steps_with_llm(
    *,
    title: str,
    prompt: str,
    summary: str,
    source_rows: list[dict[str, str]],
    depth_tier: str,
) -> list[str]:
    if not env_bool("MAIA_AGENT_LLM_REPORT_NEXT_STEPS_ENABLED", default=True):
        return []
    payload = {
        "title": " ".join(str(title or "").split()).strip()[:220],
        "prompt": " ".join(str(prompt or "").split()).strip()[:520],
        "summary": " ".join(str(summary or "").split()).strip()[:1200],
        "depth_tier": " ".join(str(depth_tier or "").split()).strip().lower() or "standard",
        "sources": [
            {
                "label": " ".join(str(row.get("label") or "").split()).strip()[:160],
                "url": " ".join(str(row.get("url") or "").split()).strip()[:220],
            }
            for row in list(source_rows or [])[:80]
        ],
    }
    response = call_json_response(
        system_prompt=(
            "You write practical, high-signal next-step recommendations for executive research deliverables. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "next_steps": ["actionable step 1", "actionable step 2"] }\n'
            "Rules:\n"
            "- Provide 3-10 specific, actionable next steps.\n"
            "- Focus on verification, decision-making, and execution priorities.\n"
            "- No generic filler and no placeholder language.\n"
            "- Keep each step under 160 characters.\n"
            "- Do not invent facts.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.2,
        timeout_seconds=12,
        max_tokens=900,
    )
    rows = response.get("next_steps") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        return []
    clean: list[str] = []
    seen: set[str] = set()
    for item in rows:
        line = " ".join(str(item or "").split()).strip()
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append(line[:160])
        if len(clean) >= 18:
            break
    return clean


def _draft_report_markdown_with_llm(
    *,
    title: str,
    prompt: str,
    summary: str,
    source_rows: list[dict[str, str]],
    evidence_findings_block: str,
    annotated_sources_block: str,
    required_facts: list[str],
    analysis_paragraphs: list[str],
    highlight_lines: list[str],
    action_lines: list[str],
    analytics_lines: list[str],
    contradiction_lines: list[str],
    depth_tier: str,
) -> str:
    if not env_bool("MAIA_AGENT_LLM_REPORT_COMPOSER_ENABLED", default=True):
        return ""
    deep_mode = str(depth_tier or "").strip().lower() in {"deep_research", "deep_analytics", "expert"}
    min_chars = 2600 if deep_mode else 1200
    max_chars = 18000 if deep_mode else 9000
    source_payload = [
        {
            "label": " ".join(str(row.get("label") or "").split()).strip()[:180],
            "url": " ".join(str(row.get("url") or "").split()).strip()[:240],
            "snippet": " ".join(str(row.get("snippet") or "").split()).strip()[:300],
        }
        for row in list(source_rows or [])[:160]
    ]
    payload = {
        "title": " ".join(str(title or "").split()).strip()[:220],
        "prompt": " ".join(str(prompt or "").split()).strip()[:700],
        "executive_summary_seed": str(summary or "").strip()[:2200],
        "depth_tier": " ".join(str(depth_tier or "").split()).strip().lower() or "standard",
        "evidence_findings_markdown_block": str(evidence_findings_block or "").strip()[:12000],
        "annotated_sources_markdown_block": str(annotated_sources_block or "").strip()[:9000],
        "required_facts": [
            " ".join(str(item or "").split()).strip()[:220]
            for item in list(required_facts or [])[:6]
            if " ".join(str(item or "").split()).strip()
        ],
        "analysis_paragraphs": [str(item or "").strip()[:1200] for item in list(analysis_paragraphs or [])[:40]],
        "highlights": [
            " ".join(str(item or "").lstrip("- ").split()).strip()[:220]
            for item in list(highlight_lines or [])[:40]
        ],
        "next_steps": [
            " ".join(str(item or "").lstrip("- ").split()).strip()[:220]
            for item in list(action_lines or [])[:30]
        ],
        "analytics_markdown_block": "\n".join(list(analytics_lines or [])[:320])[:12000],
        "contradictions_markdown_block": "\n".join(list(contradiction_lines or [])[:220])[:8000],
        "sources": source_payload,
    }
    response = call_text_response(
        system_prompt=(
            "You write premium, evidence-grounded research reports for executive audiences. "
            "Use Apple-style clarity: elegant, restrained, and highly structured. "
            "Produce markdown only."
        ),
        user_prompt=(
            "Create a complete report in markdown.\n"
            "Requirements:\n"
            "- Tailor section titles to the exact request; avoid fixed reusable templates.\n"
            "- Keep a professional, concise, high-credibility tone with Apple-style clarity: simple, precise, and visually clean.\n"
            "- Include a dedicated key-findings section with 3-5 evidence-backed findings before broader analysis.\n"
            "- Integrate provided analysis/highlights/next_steps into a coherent narrative.\n"
            "- Open with an executive summary paragraph that answers the request directly.\n"
            "- If required_facts are provided, address each one explicitly in the body unless the evidence is genuinely missing.\n"
            "- Convert the evidence_findings_markdown_block into polished prose or bullets instead of ignoring it.\n"
            "- Every major finding must include a plain-language explanation immediately after the evidence-backed claim.\n"
            "- Use inline markdown links for sources where URLs are provided, and attach links immediately after the claim they support.\n"
            "- Where multiple sources support the same claim, cite the strongest two links in the same paragraph or bullet.\n"
            "- Label the strongest source behind each major finding with a source era marker such as `foundational: 1997` or `validation: 2019`.\n"
            "- Include a final `## Sources` section with 5-7 annotated bullet citations using markdown links.\n"
            "- The sources section must describe why each source matters, not just list links.\n"
            "- If evidence is limited, state uncertainty explicitly and avoid invented claims.\n"
            "- Do not include placeholders like [Your Name] or [Your Position].\n"
            "- Do not include recipient email addresses.\n"
            f"- Target approximately {min_chars}-{max_chars} characters.\n\n"
            "Output format:\n"
            "- Start with `## <request-specific title>`.\n"
            "- Use 3-6 sections with clear hierarchy unless the evidence clearly requires more.\n"
            "- Include a final section with concrete next actions.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.25,
        timeout_seconds=22,
        max_tokens=5200,
    )
    clean = str(response or "").strip()
    if not clean:
        return ""
    clean = _sanitize_report_markdown_output(clean)
    if not clean:
        return ""
    if not clean.startswith("## "):
        clean = f"## {(' '.join(str(title or '').split()).strip() or 'Research Report')}\n\n{clean}"
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    if len(clean) < max(600, int(min_chars * 0.45)):
        return ""
    if len(clean) > int(max_chars * 1.45):
        clean = clean[: int(max_chars * 1.45)].rstrip()
    return clean
