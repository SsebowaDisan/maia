"""RAG Pipeline Phase 5: Chunk — structure-aware splitting with full provenance."""

from __future__ import annotations

import re
import uuid

from api.services.rag.types import (
    Chunk,
    EvidenceSpan,
    FormulaSpan,
    HeadingSpan,
    NormalizedDocument,
    RAGConfig,
    SourceRecord,
    TableSpan,
)

# ── Tokenizer approximation ────────────────────────────────────────────────
# We approximate tokens as ~4 characters (GPT-class tokenizers average
# around 3.5–4.5 chars per token for English). This avoids a tiktoken
# dependency while staying close enough for chunk sizing.

_CHARS_PER_TOKEN = 4


def _token_len(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


# ── Sentence splitting ─────────────────────────────────────────────────────

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, keeping delimiters attached."""
    parts = _SENTENCE_RE.split(text)
    return [p for p in parts if p.strip()]


# ── Heading path tracker ───────────────────────────────────────────────────


class _HeadingTracker:
    """Maintain a stack of headings to build heading_path for each chunk."""

    def __init__(self, headings: list[HeadingSpan]) -> None:
        # Sort headings by char_start
        self._headings = sorted(headings, key=lambda h: h.char_start)
        self._stack: list[tuple[int, str]] = []  # (level, text)
        self._idx = 0

    def advance_to(self, char_pos: int) -> list[str]:
        """Consume headings up to char_pos and return the current heading path."""
        while self._idx < len(self._headings) and self._headings[self._idx].char_start <= char_pos:
            h = self._headings[self._idx]
            # Pop headings at same or deeper level
            while self._stack and self._stack[-1][0] >= h.level:
                self._stack.pop()
            self._stack.append((h.level, h.text.strip()))
            self._idx += 1
        return [t for _, t in self._stack]


# ── Atomic chunk builders (formulas & tables) ──────────────────────────────


def _formula_chunk(
    formula: FormulaSpan,
    source: SourceRecord,
    heading_path: list[str],
) -> Chunk:
    return Chunk(
        id=str(uuid.uuid4()),
        source_id=source.id,
        text=formula.text,
        page_start=formula.page,
        page_end=formula.page,
        char_start=formula.char_start,
        char_end=formula.char_end,
        heading_path=list(heading_path),
        spans=[
            EvidenceSpan(
                text=formula.text,
                source_id=source.id,
                page=formula.page,
                char_start=formula.char_start,
                char_end=formula.char_end,
                bbox=formula.bbox,
            )
        ],
        formulas=[formula],
        chunk_type="formula",
        group_id=source.group_id,
        owner_id=source.owner_id,
        filename=source.filename,
        source_type=source.source_type.value if hasattr(source.source_type, "value") else str(source.source_type),
    )


def _table_chunk(
    table: TableSpan,
    source: SourceRecord,
    heading_path: list[str],
) -> Chunk:
    return Chunk(
        id=str(uuid.uuid4()),
        source_id=source.id,
        text=table.text,
        page_start=table.page,
        page_end=table.page,
        char_start=table.char_start,
        char_end=table.char_end,
        heading_path=list(heading_path),
        spans=[
            EvidenceSpan(
                text=table.text,
                source_id=source.id,
                page=table.page,
                char_start=table.char_start,
                char_end=table.char_end,
                bbox=table.bbox,
            )
        ],
        tables=[table],
        chunk_type="table",
        group_id=source.group_id,
        owner_id=source.owner_id,
        filename=source.filename,
        source_type=source.source_type.value if hasattr(source.source_type, "value") else str(source.source_type),
    )


# ── Core text chunker ──────────────────────────────────────────────────────


def _chunk_text_spans(
    spans: list[EvidenceSpan],
    source: SourceRecord,
    heading_tracker: _HeadingTracker,
    max_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    """Split a list of evidence spans into token-bounded chunks.

    Strategy:
      1. Group by paragraph spans (natural boundaries)
      2. Accumulate paragraphs until we hit max_tokens
      3. If a single paragraph exceeds max_tokens, split by sentences
      4. Each chunk inherits the spans it covers
    """
    chunks: list[Chunk] = []
    buffer_spans: list[EvidenceSpan] = []
    buffer_tokens = 0

    def flush() -> None:
        nonlocal buffer_spans, buffer_tokens
        if not buffer_spans:
            return

        text = "\n".join(s.text for s in buffer_spans)
        page_start = min(s.page for s in buffer_spans)
        page_end = max(s.page for s in buffer_spans)
        char_start = buffer_spans[0].char_start
        char_end = buffer_spans[-1].char_end
        heading_path = heading_tracker.advance_to(char_start)

        chunks.append(
            Chunk(
                id=str(uuid.uuid4()),
                source_id=source.id,
                text=text,
                page_start=page_start,
                page_end=page_end,
                char_start=char_start,
                char_end=char_end,
                heading_path=list(heading_path),
                spans=list(buffer_spans),
                chunk_type="text",
                group_id=source.group_id,
                owner_id=source.owner_id,
                filename=source.filename,
                source_type=source.source_type.value if hasattr(source.source_type, "value") else str(source.source_type),
            )
        )

        # Keep overlap from the tail
        if overlap_tokens > 0 and len(buffer_spans) > 1:
            overlap_spans: list[EvidenceSpan] = []
            overlap_tok = 0
            for s in reversed(buffer_spans):
                t = _token_len(s.text)
                if overlap_tok + t > overlap_tokens:
                    break
                overlap_spans.insert(0, s)
                overlap_tok += t
            buffer_spans = overlap_spans
            buffer_tokens = overlap_tok
        else:
            buffer_spans = []
            buffer_tokens = 0

    for span in spans:
        span_tokens = _token_len(span.text)

        # If a single span exceeds max_tokens, split it by sentences
        if span_tokens > max_tokens:
            flush()
            sentences = _split_sentences(span.text)
            sent_cursor = span.char_start

            for sent in sentences:
                sent_end = sent_cursor + len(sent)
                sub_span = EvidenceSpan(
                    text=sent,
                    source_id=span.source_id,
                    page=span.page,
                    char_start=sent_cursor,
                    char_end=sent_end,
                    bbox=span.bbox,
                    paragraph_index=span.paragraph_index,
                    heading_path=span.heading_path,
                    confidence=span.confidence,
                )
                sub_tokens = _token_len(sent)

                if buffer_tokens + sub_tokens > max_tokens:
                    flush()
                buffer_spans.append(sub_span)
                buffer_tokens += sub_tokens
                sent_cursor = sent_end + 1  # +1 for space
            continue

        if buffer_tokens + span_tokens > max_tokens:
            flush()

        buffer_spans.append(span)
        buffer_tokens += span_tokens

    flush()
    return chunks


# ── Section splitting (by headings first) ───────────────────────────────────


def _group_spans_by_heading(
    pages: list,  # NormalizedPage
    headings: list[HeadingSpan],
) -> list[list[EvidenceSpan]]:
    """Group evidence spans by heading boundaries.

    Returns sections where each section is a list of spans that fall between
    two consecutive headings (or start/end of document).
    """
    # Flatten all spans across pages, sorted by char_start
    all_spans: list[EvidenceSpan] = []
    for page in pages:
        all_spans.extend(page.spans)
    all_spans.sort(key=lambda s: s.char_start)

    if not all_spans:
        return []

    if not headings:
        return [all_spans]

    sorted_headings = sorted(headings, key=lambda h: h.char_start)

    sections: list[list[EvidenceSpan]] = []
    heading_idx = 0
    current_section: list[EvidenceSpan] = []

    for span in all_spans:
        # If we've passed the next heading boundary, start a new section
        while (
            heading_idx < len(sorted_headings)
            and span.char_start >= sorted_headings[heading_idx].char_start
            and current_section  # don't create empty sections
        ):
            sections.append(current_section)
            current_section = []
            heading_idx += 1
        current_section.append(span)

    if current_section:
        sections.append(current_section)

    return sections


# ── Public API ──────────────────────────────────────────────────────────────


async def chunk_document(
    normalized: NormalizedDocument,
    source: SourceRecord,
    config: RAGConfig,
) -> list[Chunk]:
    """Structure-aware chunking that never splits formulas or tables.

    Strategy:
      1. Emit formulas and tables as atomic chunks
      2. Split remaining text by heading boundaries (sections)
      3. Within each section, accumulate paragraphs up to chunk_size
      4. If a paragraph is too long, split by sentences
      5. Every chunk carries page, char offsets, heading_path, and spans
    """
    max_tokens = config.chunk_size or 10000  # 0 = effectively no limit
    overlap_tokens = config.chunk_overlap or 0
    heading_tracker = _HeadingTracker(normalized.headings)

    chunks: list[Chunk] = []

    # ── Atomic formula chunks ───────────────────────────────────────────
    formula_ranges: set[tuple[int, int]] = set()
    if config.preserve_formulas:
        for formula in normalized.formulas:
            hp = heading_tracker.advance_to(formula.char_start)
            chunks.append(_formula_chunk(formula, source, hp))
            formula_ranges.add((formula.char_start, formula.char_end))

    # ── Atomic table chunks ─────────────────────────────────────────────
    table_ranges: set[tuple[int, int]] = set()
    if config.preserve_tables:
        for table in normalized.tables:
            hp = heading_tracker.advance_to(table.char_start)
            chunks.append(_table_chunk(table, source, hp))
            table_ranges.add((table.char_start, table.char_end))

    # ── Filter out spans already covered by formula/table chunks ────────
    excluded = formula_ranges | table_ranges

    def _is_excluded(span: EvidenceSpan) -> bool:
        return (span.char_start, span.char_end) in excluded

    filtered_pages = []
    for page in normalized.pages:
        filtered_spans = [s for s in page.spans if not _is_excluded(s)]
        if filtered_spans:
            filtered_pages.append(filtered_spans)

    # ── Group by headings then chunk ────────────────────────────────────
    sections = _group_spans_by_heading(normalized.pages, normalized.headings)

    # Reset heading tracker for the text pass
    heading_tracker = _HeadingTracker(normalized.headings)

    for section_spans in sections:
        # Exclude spans already emitted as atomic chunks
        text_spans = [s for s in section_spans if not _is_excluded(s)]
        if not text_spans:
            continue
        section_chunks = _chunk_text_spans(
            text_spans, source, heading_tracker, max_tokens, overlap_tokens,
        )
        chunks.extend(section_chunks)

    return chunks
