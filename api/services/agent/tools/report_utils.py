from __future__ import annotations

import re
from typing import Any

from api.services.agent.tools.base import ToolTraceEvent

SCENE_SURFACE_SYSTEM = "system"
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}")
REQUEST_STYLE_RE = re.compile(
    r"^\s*(make|create|generate|research|analy[sz]e|write|prepare|do|build)\b",
    flags=re.IGNORECASE,
)
STOPWORDS = {
    "about", "after", "also", "among", "been", "being", "between",
    "from", "have", "into", "more", "most", "such", "than", "that",
    "their", "there", "these", "this", "those", "using", "with", "which",
}
THEME_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Model Architectures and Learning Paradigms",
        ("transformer", "foundation", "llm", "attention", "diffusion",
         "multimodal", "self-supervised", "transfer", "fine-tuning"),
    ),
    (
        "Efficiency, Scale, and Deployment",
        ("quantization", "distillation", "sparsity", "moe", "mixture",
         "inference", "latency", "edge", "throughput", "optimization"),
    ),
    (
        "Reliability, Evaluation, and Governance",
        ("evaluation", "benchmark", "robustness", "safety", "alignment",
         "bias", "risk", "trust", "governance", "hallucination"),
    ),
    (
        "Industry Applications and Business Impact",
        ("healthcare", "finance", "vision", "language", "robotics",
         "manufacturing", "operations", "automation", "customer", "enterprise"),
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
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    clean = re.sub(r"\n[ \t]+", "\n", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


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
    for idx, row in enumerate(rows[: max(1, int(limit))], start=1):
        label = str(row.get("label") or "").strip() or "Source"
        url = str(row.get("url") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        ref_num = f"[{idx}]"
        if url:
            line = f"{ref_num} [{label}]({url})"
        else:
            line = f"{ref_num} {label}"
        if snippet:
            line = f"{line} — {snippet}"
        lines.append(line)
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
