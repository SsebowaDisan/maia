from __future__ import annotations

from collections import Counter
import re
from typing import Any

from sqlmodel import Session, select

from api.context import get_context
from api.services.agent.llm_runtime import call_json_response, env_bool
from api.services.agent.tools.theater_cursor import with_scene
from ktem.db.models import engine

from ktem.db.models import engine

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
STOPWORDS = {
    "about",
    "after",
    "also",
    "because",
    "before",
    "being",
    "between",
    "company",
    "could",
    "document",
    "file",
    "files",
    "from",
    "have",
    "into",
    "more",
    "most",
    "other",
    "page",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "using",
    "with",
    "your",
}


def _normalize_color(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "green":
        return "green"
    return "yellow"


def _normalize_file_ids(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    cleaned = [str(item).strip() for item in raw if str(item).strip()]
    return list(dict.fromkeys(cleaned))


def _as_bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(low, min(high, parsed))


def _safe_snippet(text: str, *, limit: int = 220) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: max(1, limit - 1)].rstrip()}..."


def _page_number_from_label(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        parsed = int(match.group(0))
    except Exception:
        return None
    if parsed <= 0:
        return None
    return parsed


def _build_pdf_scan_steps(
    *,
    chunks: list[dict[str, Any]],
    highlights: list[dict[str, str]],
    max_pages: int = 8,
) -> list[dict[str, Any]]:
    page_rows: list[dict[str, Any]] = []

    def _append(
        *,
        source_id: str,
        source_name: str,
        page_label: str,
        snippet: str,
    ) -> None:
        cleaned_source_id = str(source_id or "").strip()
        cleaned_source_name = str(source_name or "Indexed file").strip() or "Indexed file"
        cleaned_page_label = str(page_label or "").strip()
        cleaned_snippet = _safe_snippet(snippet, limit=180)
        page_rows.append(
            {
                "source_id": cleaned_source_id,
                "source_name": cleaned_source_name,
                "page_label": cleaned_page_label,
                "page_number": _page_number_from_label(cleaned_page_label),
                "snippet": cleaned_snippet,
            }
        )

    for row in highlights:
        if not isinstance(row, dict):
            continue
        _append(
            source_id=str(row.get("source_id") or ""),
            source_name=str(row.get("source_name") or "Indexed file"),
            page_label=str(row.get("page_label") or ""),
            snippet=str(row.get("snippet") or row.get("word") or "").strip(),
        )

    for row in chunks:
        if not isinstance(row, dict):
            continue
        _append(
            source_id=str(row.get("source_id") or ""),
            source_name=str(row.get("source_name") or "Indexed file"),
            page_label=str(row.get("page_label") or ""),
            snippet=str(row.get("text") or "").strip(),
        )

    if not page_rows:
        return []

    deduped: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, int | None]] = set()
    for row in page_rows:
        key = (
            str(row.get("source_name") or "").strip().lower(),
            str(row.get("page_label") or "").strip().lower(),
            row.get("page_number") if isinstance(row.get("page_number"), int) else None,
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(row)

    deduped.sort(
        key=lambda row: (
            str(row.get("source_name") or "").strip().lower(),
            row.get("page_number") if isinstance(row.get("page_number"), int) else 10_000_000,
            str(row.get("page_label") or "").strip().lower(),
        )
    )
    limited = deduped[: max(1, int(max_pages))]
    total = len(limited)
    if total <= 0:
        return []

    output: list[dict[str, Any]] = []
    previous_page_number: int | None = None
    for index, row in enumerate(limited, start=1):
        page_number = row.get("page_number")
        if not isinstance(page_number, int):
            page_number = index
        if previous_page_number is None:
            direction = "down"
        else:
            direction = "up" if page_number < previous_page_number else "down"
        previous_page_number = page_number
        scroll_percent = (
            0.0 if total == 1 else round(((index - 1) / max(1, total - 1)) * 100.0, 2)
        )
        output.append(
            {
                "source_id": str(row.get("source_id") or ""),
                "source_name": str(row.get("source_name") or "Indexed file"),
                "page_label": str(row.get("page_label") or ""),
                "page_number": page_number,
                "page_index": index,
                "page_total": total,
                "scroll_percent": scroll_percent,
                "scroll_direction": direction,
                "snippet": str(row.get("snippet") or "").strip(),
            }
        )
    return output


def _is_pdf_name(value: Any) -> bool:
    return str(value or "").strip().lower().endswith(".pdf")


def _pdf_scene_payload(
    *,
    lane: str,
    page_index: int,
    page_total: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return with_scene(
        payload or {},
        scene_surface="document",
        lane=lane,
        primary_index=max(1, int(page_index)),
        secondary_index=max(1, int(page_total)),
    )


def _document_scene_payload(
    *,
    lane: str,
    primary_index: int = 1,
    secondary_index: int = 1,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return with_scene(
        payload or {},
        scene_surface="document",
        lane=lane,
        primary_index=max(1, int(primary_index)),
        secondary_index=max(1, int(secondary_index)),
    )


def _extract_terms(prompt: str, params: dict[str, Any], chunks: list[dict[str, Any]]) -> list[str]:
    provided = params.get("words")
    words: list[str] = []
    if isinstance(provided, list):
        words.extend(str(item).strip().lower() for item in provided if str(item).strip())
    if words:
        return list(dict.fromkeys(words))[:10]

    prompt_terms = [match.group(0).lower() for match in WORD_RE.finditer(str(prompt or ""))]
    prompt_terms = [term for term in prompt_terms if len(term) >= 4 and term not in STOPWORDS]
    if prompt_terms:
        return list(dict.fromkeys(prompt_terms))[:10]

    corpus = " ".join(str(row.get("text") or "") for row in chunks[:18])
    counts = Counter(match.group(0).lower() for match in WORD_RE.finditer(corpus))
    ranked = [word for word, _ in counts.most_common(12) if word not in STOPWORDS and len(word) >= 4]
    return ranked[:10]


def _load_source_chunks(
    *,
    user_id: str,
    file_ids: list[str],
    index_id: int | None,
    max_sources: int = 8,
    max_chunks: int = 28,
    prefer_pdf: bool = True,
    allow_recent_index_fallback: bool = False,
) -> list[dict[str, Any]]:
    if not file_ids and not allow_recent_index_fallback:
        return []
    context = get_context()
    index = context.get_index(index_id)
    Source = index._resources["Source"]
    IndexTable = index._resources["Index"]
    doc_store = index._resources["DocStore"]
    is_private = bool(index.config.get("private", False))

    source_ids: list[str] = []
    source_names: dict[str, str] = {}
    max_sources_bound = max(1, int(max_sources))
    with Session(engine) as session:
        if file_ids:
            stmt = select(Source.id, Source.name).where(Source.id.in_(file_ids))
        else:
            stmt = select(Source.id, Source.name).order_by(Source.date_created.desc())  # type: ignore[attr-defined]
            stmt = stmt.limit(max(24, max_sources_bound * 3))
        if is_private:
            stmt = stmt.where(Source.user == user_id)
        rows = session.execute(stmt).all()
        candidates: list[tuple[str, str]] = []
        for row in rows[: max(24, max_sources_bound * 4)]:
            source_id = str(row[0] or "").strip()
            if not source_id:
                continue
            source_name = str(row[1] or "Indexed file").strip() or "Indexed file"
            candidates.append((source_id, source_name))

        if prefer_pdf:
            candidates.sort(
                key=lambda row: (
                    0 if _is_pdf_name(row[1]) else 1,
                    str(row[1]).lower(),
                )
            )
        else:
            candidates.sort(key=lambda row: str(row[1]).lower())

        for source_id, source_name in candidates[:max_sources_bound]:
            source_ids.append(source_id)
            source_names[source_id] = source_name

        if not source_ids:
            return []

        rel_stmt = (
            select(IndexTable.target_id, IndexTable.source_id)
            .where(
                IndexTable.relation_type == "document",
                IndexTable.source_id.in_(source_ids),
            )
            .limit(max(60, max_chunks * 6))
        )
        rel_rows = session.execute(rel_stmt).all()

    if not rel_rows:
        return []

    target_to_source: dict[str, str] = {}
    target_ids: list[str] = []
    for target_id, source_id in rel_rows:
        doc_id = str(target_id or "").strip()
        source_key = str(source_id or "").strip()
        if not doc_id or not source_key:
            continue
        target_to_source[doc_id] = source_key
        target_ids.append(doc_id)

    if not target_ids:
        return []

    try:
        docs = doc_store.get(target_ids)
    except Exception:
        return []

    chunks: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    per_source_counts: dict[str, int] = {}
    per_source_cap = max(2, min(10, max(2, int(max_chunks // max(1, max_sources_bound)))))
    for doc in docs or []:
        doc_id = str(getattr(doc, "doc_id", "") or "").strip()
        source_id = target_to_source.get(doc_id, "")
        if not source_id:
            continue
        used = int(per_source_counts.get(source_id) or 0)
        if used >= per_source_cap:
            continue
        metadata = getattr(doc, "metadata", {}) or {}
        text = _safe_snippet(str(getattr(doc, "text", "") or ""), limit=1200)
        if not text or text in seen_text:
            continue
        seen_text.add(text)
        per_source_counts[source_id] = used + 1
        chunks.append(
            {
                "source_id": source_id,
                "source_name": source_names.get(source_id, "Indexed file"),
                "page_label": str(metadata.get("page_label") or "").strip(),
                "text": text,
            }
        )
        if len(chunks) >= max(1, int(max_chunks)):
            break
    return chunks


def _synthesize_file_with_llm(
    chunks: list[dict[str, Any]],
    *,
    source_name: str,
    topic: str,
) -> str:
    """Use an LLM to extract key findings from a single file's chunks.

    Returns a concise synthesis (3-5 sentences) of the file's most relevant
    claims and data points relative to the research topic. Falls back to the
    first chunk's text when LLM is disabled or fails.
    """
    if not env_bool("MAIA_AGENT_LLM_FILE_SYNTHESIS_ENABLED", default=True):
        return _safe_snippet(str(chunks[0].get("text") or "") if chunks else "", limit=300)

    excerpts = []
    for chunk in chunks[:12]:
        text = _safe_snippet(str(chunk.get("text") or ""), limit=400)
        if text:
            excerpts.append(text)
    if not excerpts:
        return ""

    payload = {
        "source_name": " ".join(str(source_name or "").split()).strip()[:180],
        "topic": " ".join(str(topic or "").split()).strip()[:220],
        "excerpts": excerpts,
    }
    response = call_json_response(
        system_prompt=(
            "You extract concise, evidence-grounded key findings from document excerpts "
            "for enterprise research reports. Return strict JSON only."
        ),
        user_prompt=(
            "Read the document excerpts below and extract the most relevant findings "
            "for the given research topic.\n"
            "Return JSON only in this schema:\n"
            '{ "synthesis": "3-5 sentence summary of key claims and data points." }\n'
            "Rules:\n"
            "- Focus on specific facts, figures, dates, and conclusions — not general statements.\n"
            "- Only use information present in the provided excerpts.\n"
            "- Do not fabricate facts, URLs, or company names.\n"
            "- Keep the synthesis under 400 characters.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.1,
        timeout_seconds=10,
        max_tokens=260,
    )
    if isinstance(response, dict):
        text = " ".join(str(response.get("synthesis") or "").split()).strip()
        if text:
            return text[:420]
    return _safe_snippet(excerpts[0], limit=300)


def _deep_file_source_summaries(
    chunks_by_source: dict[str, list[dict[str, Any]]],
    *,
    topic: str,
    depth_tier: str,
) -> dict[str, str]:
    """Return {source_id: synthesis_text} for all sources in a deep-research run.

    Only fires for deep_research / deep_analytics / expert tiers; returns {} otherwise.
    """
    if depth_tier not in {"deep_research", "deep_analytics", "expert"}:
        return {}
    result: dict[str, str] = {}
    for source_id, chunks in chunks_by_source.items():
        source_name = str(chunks[0].get("source_name") or "") if chunks else ""
        synthesis = _synthesize_file_with_llm(chunks, source_name=source_name, topic=topic)
        if synthesis:
            result[source_id] = synthesis
    return result


def _build_highlights(
    *,
    chunks: list[dict[str, Any]],
    terms: list[str],
    color: str,
    max_items: int = 18,
) -> list[dict[str, str]]:
    highlights: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        text = str(chunk.get("text") or "")
        lowered = text.lower()
        if not lowered:
            continue
        for term in terms:
            needle = str(term or "").strip().lower()
            if not needle:
                continue
            pos = lowered.find(needle)
            if pos < 0:
                continue
            start = max(0, pos - 80)
            end = min(len(text), pos + len(needle) + 80)
            snippet = _safe_snippet(text[start:end], limit=220)
            source_name = str(chunk.get("source_name") or "Indexed file")
            key = (needle, source_name, snippet)
            if key in seen:
                continue
            seen.add(key)
            highlights.append(
                {
                    "word": needle,
                    "color": color,
                    "snippet": snippet,
                    "source_id": str(chunk.get("source_id") or ""),
                    "source_name": source_name,
                    "page_label": str(chunk.get("page_label") or ""),
                }
            )
            if len(highlights) >= max(1, int(max_items)):
                return highlights
    return highlights


