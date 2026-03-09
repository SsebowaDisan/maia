from __future__ import annotations

import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, call_text_response, env_bool
from api.services.agent.tools.base import ToolTraceEvent

SCENE_SURFACE_SYSTEM = "system"
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}")
REQUEST_STYLE_RE = re.compile(
    r"^\s*(make|create|generate|research|analy[sz]e|write|prepare|do|build)\b",
    flags=re.IGNORECASE,
)
STOPWORDS = {
    "about",
    "after",
    "also",
    "among",
    "been",
    "being",
    "between",
    "from",
    "have",
    "into",
    "more",
    "most",
    "such",
    "than",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "using",
    "with",
    "which",
}
THEME_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Model Architectures and Learning Paradigms",
        (
            "transformer",
            "foundation",
            "llm",
            "attention",
            "diffusion",
            "multimodal",
            "self-supervised",
            "transfer",
            "fine-tuning",
        ),
    ),
    (
        "Efficiency, Scale, and Deployment",
        (
            "quantization",
            "distillation",
            "sparsity",
            "moe",
            "mixture",
            "inference",
            "latency",
            "edge",
            "throughput",
            "optimization",
        ),
    ),
    (
        "Reliability, Evaluation, and Governance",
        (
            "evaluation",
            "benchmark",
            "robustness",
            "safety",
            "alignment",
            "bias",
            "risk",
            "trust",
            "governance",
            "hallucination",
        ),
    ),
    (
        "Industry Applications and Business Impact",
        (
            "healthcare",
            "finance",
            "vision",
            "language",
            "robotics",
            "manufacturing",
            "operations",
            "automation",
            "customer",
            "enterprise",
        ),
    ),
)

def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _first_sentence(text: str, max_len: int = 220) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        return ""
    for token in (". ", "! ", "? "):
        if token in clean:
            clean = clean.split(token, 1)[0] + token.strip()
            break
    if len(clean) <= max_len:
        return clean
    return f"{clean[: max_len - 1].rstrip()}..."


def _report_delivery_targets(*, prompt: str, settings: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for match in EMAIL_RE.findall(str(prompt or "")):
        value = str(match or "").strip().lower()
        if value and value not in targets:
            targets.append(value)
    task_contract = settings.get("__task_contract")
    if isinstance(task_contract, dict):
        target_raw = " ".join(str(task_contract.get("delivery_target") or "").split()).strip()
        for match in EMAIL_RE.findall(target_raw):
            value = str(match or "").strip().lower()
            if value and value not in targets:
                targets.append(value)
    return targets[:6]


def _redact_delivery_targets(text: str, *, targets: list[str]) -> str:
    clean = str(text or "")
    if not clean or not targets:
        return clean
    for target in targets:
        if not target:
            continue
        clean = re.sub(re.escape(target), "", clean, flags=re.IGNORECASE)
    clean = " ".join(clean.split())
    return clean.strip()


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _classify_report_intent_with_llm(
    *,
    prompt: str,
    summary: str,
    title: str,
    settings: dict[str, Any],
) -> dict[str, bool]:
    if not env_bool("MAIA_AGENT_LLM_REPORT_INTENT_ENABLED", default=True):
        return {}
    payload = {
        "prompt": " ".join(str(prompt or "").split()).strip()[:520],
        "summary": " ".join(str(summary or "").split()).strip()[:520],
        "title": " ".join(str(title or "").split()).strip()[:200],
        "preferences": settings.get("__user_preferences") if isinstance(settings.get("__user_preferences"), dict) else {},
    }
    response = call_json_response(
        system_prompt=(
            "You classify report-generation intent flags for an agent. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            "{\n"
            '  "location_objective": false,\n'
            '  "direct_question": false,\n'
            '  "simple_explanation_required": false\n'
            "}\n"
            "Rules:\n"
            "- Infer only from provided input.\n"
            "- Do not fabricate facts.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.0,
        timeout_seconds=9,
        max_tokens=120,
    )
    if not isinstance(response, dict):
        return {}
    location_objective = _coerce_bool(response.get("location_objective"))
    direct_question = _coerce_bool(response.get("direct_question"))
    simple_explanation = _coerce_bool(response.get("simple_explanation_required"))
    output: dict[str, bool] = {}
    if location_objective is not None:
        output["location_objective"] = location_objective
    if direct_question is not None:
        output["direct_question"] = direct_question
    if simple_explanation is not None:
        output["simple_explanation_required"] = simple_explanation
    return output


def _extract_location_signal_with_llm(text: str) -> str:
    clean = " ".join(str(text or "").split()).strip()
    if not clean:
        return ""
    if not env_bool("MAIA_AGENT_LLM_LOCATION_SIGNAL_ENABLED", default=True):
        return ""
    response = call_json_response(
        system_prompt=(
            "Extract concrete location evidence from text. Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "location_signal": "string", "has_location_signal": false }\n'
            "Rules:\n"
            "- Keep location_signal empty when no explicit location evidence exists.\n"
            "- Do not infer or guess.\n\n"
            f"Input text:\n{clean[:1200]}"
        ),
        temperature=0.0,
        timeout_seconds=8,
        max_tokens=120,
    )
    if not isinstance(response, dict):
        return ""
    has_location = _coerce_bool(response.get("has_location_signal"))
    signal = " ".join(str(response.get("location_signal") or "").split()).strip(" .,:;")
    if has_location is False:
        return ""
    return signal[:160]


def _draft_direct_answer(question: str) -> str:
    if not env_bool("MAIA_AGENT_LLM_REPORT_QA_ENABLED", default=True):
        return ""
    payload = " ".join(str(question or "").split()).strip()
    if not payload:
        return ""
    from api.services.agent.tools import data_tools as data_tools_module

    response = data_tools_module.call_text_response(
        system_prompt=(
            "You answer user questions clearly and concisely for enterprise reports. "
            "Do not mention tools or execution steps."
        ),
        user_prompt=(
            "Provide a direct answer in 2-5 sentences.\n"
            "If confidence is low, state uncertainty briefly.\n\n"
            f"Question:\n{payload}"
        ),
        temperature=0.1,
        timeout_seconds=10,
        max_tokens=260,
    )
    clean = " ".join(str(response or "").split()).strip()
    if not clean:
        return ""
    if len(clean) > 900:
        return f"{clean[:899].rstrip()}..."
    return clean


def _prefers_simple_explanation(
    *,
    prompt: str,
    summary: str,
    title: str,
    settings: dict[str, Any],
    llm_intent_flags: dict[str, bool] | None = None,
) -> bool:
    if bool(settings.get("__simple_explanation_required")):
        return True
    if isinstance(llm_intent_flags, dict) and bool(llm_intent_flags.get("simple_explanation_required")):
        return True
    prefs = settings.get("__user_preferences")
    if not isinstance(prefs, dict):
        prefs = {}
    explicit_pref = _coerce_bool(prefs.get("simple_explanation_required"))
    if explicit_pref is not None:
        return explicit_pref
    inferred = _classify_report_intent_with_llm(
        prompt=prompt,
        summary=summary,
        title=title,
        settings=settings,
    )
    return bool(inferred.get("simple_explanation_required"))


def _normalize_source_rows(raw: Any, *, limit: int = 12) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("snippet") or item.get("excerpt") or "").strip()
        metadata = item.get("metadata")
        if not snippet and isinstance(metadata, dict):
            snippet = str(metadata.get("excerpt") or metadata.get("summary") or "").strip()
        if not label and not url:
            continue
        normalized.append(
            {
                "label": label or url,
                "url": url,
                "snippet": _first_sentence(snippet, max_len=180),
            }
        )
        if len(normalized) >= max(1, int(limit)):
            break
    return normalized


def _topic_label(*, title: str, prompt: str, summary: str) -> str:
    preferred = " ".join(str(title or "").split()).strip()
    if preferred and preferred.lower() not in {"executive report", "website analysis report"}:
        return preferred
    fallback = " ".join(str(summary or "").split()).strip()
    if fallback and len(fallback) <= 120 and not REQUEST_STYLE_RE.match(fallback):
        return fallback
    prompt_clean = " ".join(str(prompt or "").split()).strip()
    if prompt_clean:
        trimmed = prompt_clean.rstrip("?.!")
        if len(trimmed) > 140:
            trimmed = f"{trimmed[:139].rstrip()}..."
        return trimmed
    return "the requested topic"


def _top_terms_from_sources(source_rows: list[dict[str, str]], *, limit: int = 6) -> list[str]:
    counts: dict[str, int] = {}
    for row in source_rows:
        joined = " ".join([str(row.get("label") or ""), str(row.get("snippet") or "")]).lower()
        for match in WORD_RE.finditer(joined):
            token = match.group(0).lower()
            if len(token) < 4 or token in STOPWORDS:
                continue
            counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[: max(1, int(limit))]]


def _theme_examples(source_rows: list[dict[str, str]]) -> list[tuple[str, list[str]]]:
    theme_rows: dict[str, list[str]] = {name: [] for name, _ in THEME_KEYWORDS}
    generic_rows: list[str] = []
    for row in source_rows:
        snippet = " ".join(str(row.get("snippet") or "").split()).strip()
        label = " ".join(str(row.get("label") or "").split()).strip()
        if not snippet:
            if label:
                snippet = label
            else:
                continue
        lowered = snippet.lower()
        matched_theme = ""
        for theme_name, keywords in THEME_KEYWORDS:
            if any(keyword in lowered for keyword in keywords):
                matched_theme = theme_name
                break
        if matched_theme:
            if snippet not in theme_rows[matched_theme]:
                theme_rows[matched_theme].append(snippet)
        else:
            if snippet not in generic_rows:
                generic_rows.append(snippet)

    ordered: list[tuple[str, list[str]]] = []
    for theme_name, _ in THEME_KEYWORDS:
        rows = theme_rows.get(theme_name) or []
        if rows:
            ordered.append((theme_name, rows[:3]))
    if not ordered and generic_rows:
        ordered.append(("Cross-cutting Findings", generic_rows[:3]))
    return ordered[:4]


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
    min_paragraphs = 6 if deep_mode else 3
    max_paragraphs = 12 if deep_mode else 6
    payload = {
        "title": " ".join(str(title or "").split()).strip()[:220],
        "summary": " ".join(str(summary or "").split()).strip()[:1200],
        "prompt": " ".join(str(prompt or "").split()).strip()[:520],
        "depth_tier": depth_tier,
        "sources_preview": source_rows[:16] if deep_mode else source_rows[:8],
    }
    response = call_json_response(
        system_prompt=(
            "Write professional, evidence-grounded analysis paragraphs for executive research reports. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "analysis_paragraphs": ["paragraph one", "paragraph two"] }\n'
            "Rules:\n"
            f"- Provide {min_paragraphs}-{max_paragraphs} substantive paragraphs.\n"
            "- Cover mechanisms, evidence patterns, trade-offs, and practical implications.\n"
            "- Use only provided context; avoid fabrications.\n"
            "- Keep each paragraph between 1-4 sentences.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.2,
        timeout_seconds=12,
        max_tokens=700,
    )
    rows = response.get("analysis_paragraphs") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        return []
    cleaned: list[str] = []
    for item in rows[:max_paragraphs]:
        line = " ".join(str(item or "").split()).strip()
        if not line:
            continue
        cleaned.append(line[:1200])
    if deep_mode:
        total_chars = sum(len(item) for item in cleaned)
        if len(cleaned) < min_paragraphs or total_chars < 1300:
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
        (
            "From an execution standpoint, the strongest near-term value comes from targeted pilot deployments, "
            "clear evaluation criteria, and continuous monitoring for reliability drift."
        )
    )
    paragraphs.append(
        (
            "Risk posture should account for data quality, reproducibility, model behavior under distribution shift, "
            "and governance requirements before scaling to customer-facing or regulated workflows."
        )
    )
    if depth_tier in {"deep_research", "deep_analytics", "expert"}:
        paragraphs.append(
            (
                "Recommended follow-up is to expand primary-source coverage on unresolved claims, quantify performance/cost trade-offs, "
                "and maintain a living evidence log that can support auditability."
            )
        )
    return paragraphs[:10]


def _auto_highlights_from_sources(rows: list[dict[str, str]], *, limit: int = 6) -> list[str]:
    output: list[str] = []
    for row in rows:
        label = str(row.get("label") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        if label and snippet:
            output.append(f"{label}: {snippet}")
        elif label:
            output.append(label)
        if len(output) >= max(1, int(limit)):
            break
    return output


def _reference_lines(rows: list[dict[str, str]], *, limit: int = 8) -> list[str]:
    lines: list[str] = []
    for row in rows[: max(1, int(limit))]:
        label = str(row.get("label") or "").strip() or "Source"
        url = str(row.get("url") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        if url:
            line = f"- [{label}]({url})"
        else:
            line = f"- {label}"
        if snippet:
            line = f"{line} - {snippet}"
        lines.append(line)
    return lines


def _analytics_section_lines(settings: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    profile = settings.get("__latest_data_profile")
    if isinstance(profile, dict):
        lines.extend(
            [
                "### Data Profile Snapshot",
                "| Metric | Value |",
                "|---|---|",
                f"| Rows | {int(profile.get('row_count') or 0)} |",
                f"| Columns | {int(profile.get('column_count') or 0)} |",
                f"| Numeric columns | {len(profile.get('numeric_columns') or [])} |",
            ]
        )
        correlations = profile.get("top_correlations")
        if isinstance(correlations, list) and correlations:
            lines.extend(["", "| Strong correlation | Value |", "|---|---|"])
            for item in correlations[:6]:
                if not isinstance(item, dict):
                    continue
                left = " ".join(str(item.get("left") or "").split()).strip()
                right = " ".join(str(item.get("right") or "").split()).strip()
                value = item.get("correlation")
                if not left or not right:
                    continue
                lines.append(f"| {left} vs {right} | {value} |")

    visualization = settings.get("__latest_data_visualization")
    if isinstance(visualization, dict):
        lines.extend(
            [
                "",
                "### Visualization Snapshot",
                "| Field | Value |",
                "|---|---|",
                f"| Chart type | {str(visualization.get('chart_type') or 'n/a')} |",
                f"| Rows plotted | {int(visualization.get('row_count') or 0)} |",
                f"| X axis | {str(visualization.get('x') or 'n/a')} |",
                f"| Y axis | {str(visualization.get('y') or 'n/a')} |",
                f"| Artifact path | {str(visualization.get('path') or 'n/a')} |",
            ]
        )

    ga4_report = settings.get("__latest_analytics_report")
    if isinstance(ga4_report, dict):
        dimensions = ga4_report.get("dimensions")
        metrics = ga4_report.get("metrics")
        lines.extend(
            [
                "",
                "### Analytics API Snapshot",
                "| Metric | Value |",
                "|---|---|",
                f"| Property ID | {str(ga4_report.get('property_id') or 'n/a')} |",
                f"| Rows returned | {int(ga4_report.get('row_count') or 0)} |",
                f"| Dimensions | {', '.join(str(item) for item in (dimensions or [])[:8]) or 'n/a'} |",
                f"| Metrics | {', '.join(str(item) for item in (metrics or [])[:8]) or 'n/a'} |",
            ]
        )
    ga4_full_report = settings.get("__latest_analytics_full_report")
    if isinstance(ga4_full_report, dict) and ga4_full_report:
        kpis = ga4_full_report.get("kpis")
        kpi_rows = kpis if isinstance(kpis, dict) else {}
        chart_keys = (
            [str(item).strip() for item in ga4_full_report.get("chart_keys", []) if str(item).strip()]
            if isinstance(ga4_full_report.get("chart_keys"), list)
            else []
        )
        lines.extend(
            [
                "",
                "### GA4 Full Report Snapshot",
                "| Metric | Value |",
                "|---|---|",
                f"| Property ID | {str(ga4_full_report.get('property_id') or 'n/a')} |",
                f"| Sessions (30d) | {kpi_rows.get('sessions', 'n/a')} |",
                f"| Users (30d) | {kpi_rows.get('users', 'n/a')} |",
                f"| Conversions (30d) | {kpi_rows.get('conversions', 'n/a')} |",
                f"| Bounce rate (30d) | {kpi_rows.get('bounce_rate', 'n/a')}% |",
                f"| Top channel | {str(ga4_full_report.get('top_channel') or 'n/a')} |",
                f"| Top page | {str(ga4_full_report.get('top_page') or 'n/a')} |",
                f"| Chart payloads | {len(chart_keys)} |",
            ]
        )
        if chart_keys:
            lines.append(f"| Chart keys | {', '.join(chart_keys[:8])} |")
    return lines


def _simple_explanation_lines(*, summary: str, title: str) -> list[str]:
    topic = " ".join(str(title or "").split()).strip() or "this topic"
    first = _first_sentence(summary, max_len=220)
    lines = [
        "### Simple Explanation (For a 5-Year-Old)",
        f"- Imagine **{topic}** is a puzzle. We looked at many pieces and kept the ones that really fit.",
    ]
    if first:
        lines.append(f"- Big idea: {first}")
    lines.append("- Why this helps: when facts fit together, we can make safer and smarter decisions.")
    return lines


def _event(
    *,
    tool_id: str,
    event_type: str,
    title: str,
    detail: str = "",
    data: dict[str, Any] | None = None,
) -> ToolTraceEvent:
    payload = {
        "tool_id": tool_id,
        "scene_surface": SCENE_SURFACE_SYSTEM,
    }
    if isinstance(data, dict):
        payload.update(data)
    return ToolTraceEvent(
        event_type=event_type,
        title=title,
        detail=detail,
        data=payload,
    )
