from __future__ import annotations

from collections import Counter
import re
from typing import Any

from sqlmodel import Session, select

from api.context import get_context
from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)
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
) -> list[dict[str, Any]]:
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


class DocumentHighlightExtractTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="documents.highlight.extract",
        action_class="read",
        risk_level="low",
        required_permissions=["data.read"],
        execution_policy="auto_execute",
        description="Highlight and copy matching words from selected indexed files.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        selected_file_ids = _normalize_file_ids(context.settings.get("__selected_file_ids"))
        index_id_raw = context.settings.get("__selected_index_id")
        index_id = int(index_id_raw) if isinstance(index_id_raw, int) or str(index_id_raw).isdigit() else None
        highlight_color = _normalize_color(params.get("highlight_color") or context.settings.get("__highlight_color"))
        max_sources = _as_bounded_int(
            params.get("max_sources") or context.settings.get("__file_research_max_sources"),
            default=8,
            low=1,
            high=240,
        )
        max_chunks = _as_bounded_int(
            params.get("max_chunks") or context.settings.get("__file_research_max_chunks"),
            default=28,
            low=20,
            high=3000,
        )
        max_scan_pages = _as_bounded_int(
            params.get("max_scan_pages") or context.settings.get("__file_research_max_scan_pages"),
            default=8,
            low=8,
            high=300,
        )
        max_highlights = _as_bounded_int(
            params.get("max_highlights"),
            default=96 if max_sources >= 80 else 36,
            low=12,
            high=220,
        )
        prefer_pdf_only = bool(
            params.get("prefer_pdf")
            if params.get("prefer_pdf") is not None
            else context.settings.get("__file_research_prefer_pdf", True)
        )

        chunks = _load_source_chunks(
            user_id=context.user_id,
            file_ids=selected_file_ids,
            index_id=index_id,
            max_sources=max_sources,
            max_chunks=max_chunks,
            prefer_pdf=prefer_pdf_only,
        )
        if not chunks:
            return ToolExecutionResult(
                summary="No readable file content available for highlighting.",
                content=(
                    "Unable to scan selected files for highlights.\n"
                    "- Select one or more indexed files, then rerun highlight extraction."
                ),
                data={"highlight_color": highlight_color, "highlighted_words": [], "copied_snippets": []},
                sources=[],
                next_steps=[],
                events=[
                    ToolTraceEvent(
                        event_type="document_opened",
                        title="Open selected files",
                        detail="No selected file content was available",
                    )
                ],
            )

        terms = _extract_terms(prompt, params, chunks)
        highlights = _build_highlights(
            chunks=chunks,
            terms=terms,
            color=highlight_color,
            max_items=max_highlights,
        )
        if not highlights and chunks:
            fallback_terms = _extract_terms("", {}, chunks)
            highlights = _build_highlights(
                chunks=chunks,
                terms=fallback_terms,
                color=highlight_color,
                max_items=max_highlights,
            )
            if fallback_terms:
                terms = fallback_terms

        copied_snippets = [row["snippet"] for row in highlights[:10] if row.get("snippet")]
        copied_bucket = context.settings.get("__copied_highlights")
        if not isinstance(copied_bucket, list):
            copied_bucket = []
        copy_limit = min(max_highlights, 180)
        for row in highlights[:copy_limit]:
            copied_bucket.append(
                {
                    "source": "file",
                    "color": row.get("color") or highlight_color,
                    "word": row.get("word") or "",
                    "text": row.get("snippet") or "",
                    "reference": row.get("source_name") or "Indexed file",
                    "page_label": row.get("page_label") or "",
                }
            )
        copied_cap = 400 if max_sources >= 80 else 120
        context.settings["__copied_highlights"] = copied_bucket[-copied_cap:]
        context.settings["__highlight_color"] = highlight_color

        source_summary_by_id: dict[str, dict[str, Any]] = {}
        for row in highlights:
            source_id = str(row.get("source_id") or "")
            if not source_id:
                continue
            source_name = str(row.get("source_name") or "Indexed file")
            page_label = str(row.get("page_label") or "")
            snippet = _safe_snippet(str(row.get("snippet") or ""), limit=280)
            keyword = str(row.get("word") or "").strip().lower()
            summary = source_summary_by_id.setdefault(
                source_id,
                {
                    "source_name": source_name,
                    "page_label": page_label,
                    "extract": snippet,
                    "keywords": [],
                    "highlight_count": 0,
                },
            )
            if not summary.get("page_label") and page_label:
                summary["page_label"] = page_label
            if not summary.get("extract") and snippet:
                summary["extract"] = snippet
            if keyword:
                keywords = summary.get("keywords")
                if not isinstance(keywords, list):
                    keywords = []
                    summary["keywords"] = keywords
                if keyword not in keywords and len(keywords) < 12:
                    keywords.append(keyword)
            summary["highlight_count"] = int(summary.get("highlight_count") or 0) + 1

        source_by_id: dict[str, AgentSource] = {}
        for source_id, summary in source_summary_by_id.items():
            extract_text = str(summary.get("extract") or "").strip()
            source_by_id[source_id] = AgentSource(
                source_type="file",
                label=str(summary.get("source_name") or "Indexed file"),
                file_id=source_id,
                score=0.72,
                metadata={
                    "page_label": str(summary.get("page_label") or ""),
                    "extract": extract_text,
                    "excerpt": extract_text,
                    "snippet": extract_text,
                    "keywords": list(summary.get("keywords") or [])[:12],
                    "highlight_count": int(summary.get("highlight_count") or 0),
                },
            )

        highlighted_words = [row.get("word", "") for row in highlights if row.get("word")]
        unique_words = list(dict.fromkeys(highlighted_words))
        pdf_scan_steps = _build_pdf_scan_steps(
            chunks=chunks,
            highlights=highlights,
            max_pages=max_scan_pages,
        )
        unique_sources = {
            str(row.get("source_id") or "").strip()
            for row in chunks
            if str(row.get("source_id") or "").strip()
        }
        has_pdf_file = any(
            str(row.get("source_name") or "").strip().lower().endswith(".pdf")
            for row in chunks
            if isinstance(row, dict)
        )
        is_pdf_scan = bool(pdf_scan_steps) and (
            has_pdf_file
            or any(str(row.get("page_label") or "").strip() for row in pdf_scan_steps)
        )

        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="document_opened",
                title="Open selected files",
                detail=f"Scanning {len(chunks)} file excerpt(s)",
                data={
                    "chunk_count": len(chunks),
                    "source_count": len(unique_sources),
                    "scene_surface": "document",
                },
            ),
        ]
        if is_pdf_scan and pdf_scan_steps:
            first_step = pdf_scan_steps[0]
            events.append(
                ToolTraceEvent(
                    event_type="pdf_open",
                    title="Open PDF preview",
                    detail=str(first_step.get("source_name") or "Indexed PDF"),
                    data={
                        "scene_surface": "document",
                        "source_name": str(first_step.get("source_name") or ""),
                        "pdf_page": int(first_step.get("page_number") or 1),
                        "page_index": int(first_step.get("page_index") or 1),
                        "page_total": int(first_step.get("page_total") or len(pdf_scan_steps)),
                        "pdf_total_pages": int(first_step.get("page_total") or len(pdf_scan_steps)),
                        "scroll_percent": float(first_step.get("scroll_percent") or 0.0),
                    },
                )
            )
            for step in pdf_scan_steps:
                page_number = int(step.get("page_number") or 1)
                page_index = int(step.get("page_index") or 1)
                page_total = int(step.get("page_total") or len(pdf_scan_steps))
                source_name = str(step.get("source_name") or "Indexed PDF")
                page_label = str(step.get("page_label") or "").strip()
                snippet_preview = str(step.get("snippet") or "").strip()
                direction = str(step.get("scroll_direction") or "down").strip().lower()
                if direction not in {"up", "down"}:
                    direction = "down"
                base_payload = {
                    "scene_surface": "document",
                    "source_name": source_name,
                    "source_id": str(step.get("source_id") or ""),
                    "pdf_page": page_number,
                    "page_index": page_index,
                    "page_total": page_total,
                    "pdf_total_pages": page_total,
                    "page_label": page_label,
                    "scroll_percent": float(step.get("scroll_percent") or 0.0),
                    "scroll_direction": direction,
                }
                events.append(
                    ToolTraceEvent(
                        event_type="pdf_page_change",
                        title=f"Navigate to PDF page {page_number}",
                        detail=(
                            f"{source_name} - page {page_number}"
                            if not page_label
                            else f"{source_name} - page {page_label}"
                        ),
                        data=base_payload,
                    )
                )
                events.append(
                    ToolTraceEvent(
                        event_type="pdf_scan_region",
                        title=f"Scan PDF page {page_number}",
                        detail=_safe_snippet(snippet_preview, limit=120)
                        or "Scanning visible text region",
                        data={
                            **base_payload,
                            "scan_region": _safe_snippet(snippet_preview, limit=240),
                            "scan_pass": page_index,
                        },
                    )
                )

        events.append(
            ToolTraceEvent(
                event_type="document_scanned",
                title="Scan document excerpts",
                detail=f"Detected {len(unique_words)} candidate highlighted word(s)",
                data={
                    "terms": terms[:10],
                    "highlight_color": highlight_color,
                    "scene_surface": "document",
                    "max_sources": max_sources,
                    "max_chunks": max_chunks,
                },
            )
        )
        events.append(
            ToolTraceEvent(
                event_type="highlights_detected",
                title="Highlight words in files",
                detail=", ".join(unique_words[:8]) if unique_words else "No matching words found",
                data={
                    "keywords": unique_words[:12],
                    "highlight_color": highlight_color,
                    "highlighted_words": highlights[: min(max_highlights, 120)],
                    "copied_snippets": copied_snippets[:10],
                    "page_total": len(pdf_scan_steps) if pdf_scan_steps else 0,
                    "scene_surface": "document",
                },
            )
        )
        if highlights:
            first_highlight = highlights[0]
            events.append(
                ToolTraceEvent(
                    event_type="pdf_evidence_linked",
                    title="Link highlight evidence",
                    detail=_safe_snippet(str(first_highlight.get("snippet") or ""), limit=140),
                    data={
                        "scene_surface": "document",
                        "highlight_color": highlight_color,
                        "keyword": str(first_highlight.get("word") or ""),
                        "source_name": str(first_highlight.get("source_name") or ""),
                        "page_label": str(first_highlight.get("page_label") or ""),
                    },
                )
            )
        if copied_snippets:
            events.append(
                ToolTraceEvent(
                    event_type="doc_copy_clipboard",
                    title="Copy highlighted words",
                    detail=_safe_snippet(copied_snippets[0], limit=160),
                    data={
                        "clipboard_text": copied_snippets[0],
                        "highlight_color": highlight_color,
                        "keywords": unique_words[:12],
                    },
                )
            )

        lines = [
            "### File Highlights",
            f"- Highlight color: {highlight_color}",
            f"- Source files scanned: {len(unique_sources)}",
            f"- Excerpts scanned: {len(chunks)}",
            f"- Highlighted words: {', '.join(unique_words[:12]) if unique_words else 'none'}",
        ]
        if copied_snippets:
            lines.extend(
                [
                    "",
                    "### Copied snippets",
                    *[f"- {snippet}" for snippet in copied_snippets[:6]],
                ]
            )

        return ToolExecutionResult(
            summary=f"File highlight extraction completed with {len(unique_words)} highlighted word(s).",
            content="\n".join(lines),
            data={
                "highlight_color": highlight_color,
                "keywords": unique_words[:12],
                "highlighted_words": highlights[: min(max_highlights, 120)],
                "copied_snippets": copied_snippets[:10],
                "chunk_count": len(chunks),
                "source_count": len(unique_sources),
                "max_sources": max_sources,
                "max_chunks": max_chunks,
                "max_scan_pages": max_scan_pages,
                "scene_surface": "document",
                "pdf_page": int(pdf_scan_steps[-1].get("page_number") or 1) if pdf_scan_steps else 1,
                "page_index": int(pdf_scan_steps[-1].get("page_index") or 1) if pdf_scan_steps else 1,
                "page_total": len(pdf_scan_steps),
                "pdf_total_pages": len(pdf_scan_steps),
                "scroll_percent": float(pdf_scan_steps[-1].get("scroll_percent") or 0.0)
                if pdf_scan_steps
                else 0.0,
                "scroll_direction": str(pdf_scan_steps[-1].get("scroll_direction") or "down")
                if pdf_scan_steps
                else "down",
                "scan_region": str(pdf_scan_steps[-1].get("snippet") or "") if pdf_scan_steps else "",
            },
            sources=list(source_by_id.values()),
            next_steps=[],
            events=events,
        )
