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


def _safe_snippet(text: str, *, limit: int = 220) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: max(1, limit - 1)].rstrip()}..."


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
) -> list[dict[str, Any]]:
    context = get_context()
    index = context.get_index(index_id)
    Source = index._resources["Source"]
    IndexTable = index._resources["Index"]
    doc_store = index._resources["DocStore"]
    is_private = bool(index.config.get("private", False))

    source_ids: list[str] = []
    source_names: dict[str, str] = {}
    with Session(engine) as session:
        if file_ids:
            stmt = select(Source.id, Source.name).where(Source.id.in_(file_ids))
        else:
            stmt = select(Source.id, Source.name).order_by(Source.date_created.desc())  # type: ignore[attr-defined]
            stmt = stmt.limit(max(1, int(max_sources)))
        if is_private:
            stmt = stmt.where(Source.user == user_id)
        rows = session.execute(stmt).all()
        for row in rows:
            source_id = str(row[0] or "").strip()
            if not source_id:
                continue
            source_ids.append(source_id)
            source_names[source_id] = str(row[1] or "Indexed file").strip() or "Indexed file"

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
    for doc in docs or []:
        doc_id = str(getattr(doc, "doc_id", "") or "").strip()
        source_id = target_to_source.get(doc_id, "")
        if not source_id:
            continue
        metadata = getattr(doc, "metadata", {}) or {}
        text = _safe_snippet(str(getattr(doc, "text", "") or ""), limit=1200)
        if not text or text in seen_text:
            continue
        seen_text.add(text)
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

        chunks = _load_source_chunks(
            user_id=context.user_id,
            file_ids=selected_file_ids,
            index_id=index_id,
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
                next_steps=[
                    "Select files in the workspace and rerun the highlight step.",
                    "Include explicit target words for more accurate highlighting.",
                ],
                events=[
                    ToolTraceEvent(
                        event_type="document_opened",
                        title="Open selected files",
                        detail="No selected file content was available",
                    )
                ],
            )

        terms = _extract_terms(prompt, params, chunks)
        highlights = _build_highlights(chunks=chunks, terms=terms, color=highlight_color)
        if not highlights and chunks:
            fallback_terms = _extract_terms("", {}, chunks)
            highlights = _build_highlights(chunks=chunks, terms=fallback_terms, color=highlight_color)
            if fallback_terms:
                terms = fallback_terms

        copied_snippets = [row["snippet"] for row in highlights[:10] if row.get("snippet")]
        copied_bucket = context.settings.get("__copied_highlights")
        if not isinstance(copied_bucket, list):
            copied_bucket = []
        for row in highlights[:24]:
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
        context.settings["__copied_highlights"] = copied_bucket[-64:]
        context.settings["__highlight_color"] = highlight_color

        source_by_id: dict[str, AgentSource] = {}
        for row in highlights:
            source_id = str(row.get("source_id") or "")
            if not source_id or source_id in source_by_id:
                continue
            source_by_id[source_id] = AgentSource(
                source_type="file",
                label=str(row.get("source_name") or "Indexed file"),
                file_id=source_id,
                score=0.72,
                metadata={"page_label": str(row.get("page_label") or "")},
            )

        highlighted_words = [row.get("word", "") for row in highlights if row.get("word")]
        unique_words = list(dict.fromkeys(highlighted_words))
        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="document_opened",
                title="Open selected files",
                detail=f"Scanning {len(chunks)} file excerpt(s)",
                data={"chunk_count": len(chunks)},
            ),
            ToolTraceEvent(
                event_type="document_scanned",
                title="Scan document excerpts",
                detail=f"Detected {len(unique_words)} candidate highlighted word(s)",
                data={"terms": terms[:10], "highlight_color": highlight_color},
            ),
            ToolTraceEvent(
                event_type="highlights_detected",
                title="Highlight words in files",
                detail=", ".join(unique_words[:8]) if unique_words else "No matching words found",
                data={
                    "keywords": unique_words[:12],
                    "highlight_color": highlight_color,
                    "highlighted_words": highlights[:18],
                    "copied_snippets": copied_snippets[:10],
                },
            ),
        ]
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
                "highlighted_words": highlights[:18],
                "copied_snippets": copied_snippets[:10],
                "chunk_count": len(chunks),
            },
            sources=list(source_by_id.values()),
            next_steps=[
                "Open docs and paste copied highlights into the report.",
                "Switch highlight color between yellow and green based on review context.",
            ],
            events=events,
        )
