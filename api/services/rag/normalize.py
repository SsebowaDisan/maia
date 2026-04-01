"""RAG Pipeline Phase 4: Normalize — clean text while preserving evidence geometry."""

from __future__ import annotations

import re

from api.services.rag.types import (
    EvidenceSpan,
    ExtractionResult,
    FormulaSpan,
    HeadingSpan,
    NormalizedDocument,
    NormalizedPage,
    TableSpan,
)

# ── Whitespace cleanup ─────────────────────────────────────────────────────

_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)

# Patterns that look like repeated headers/footers (page numbers, document titles)
_PAGE_NUMBER = re.compile(r"^\s*(?:Page\s+)?\d{1,4}\s*$", re.IGNORECASE)


def _clean_line(line: str) -> str:
    """Collapse multiple spaces in a single line, strip trailing whitespace."""
    line = _MULTI_SPACE.sub(" ", line)
    line = line.rstrip()
    return line


def _is_repeated_block(text: str, all_blocks: list[str], threshold: int = 3) -> bool:
    """Return True if this block appears in at least `threshold` other blocks (header/footer)."""
    stripped = text.strip()
    if not stripped or len(stripped) > 200:
        return False
    if _PAGE_NUMBER.match(stripped):
        return True
    count = sum(1 for b in all_blocks if b.strip() == stripped)
    return count >= threshold


# ── Public API ──────────────────────────────────────────────────────────────


async def normalize_document(extraction: ExtractionResult) -> NormalizedDocument:
    """Clean whitespace, remove duplicate headers/footers, update char offsets.

    Preserves formula tokens, table cell adjacency, and section/page anchors.
    Returns a NormalizedDocument with clean text + updated evidence geometry.
    """
    source_id = extraction.source_id

    # ── Step 1: Collect all raw block texts for duplicate detection ──────
    all_block_texts: list[str] = []
    for page in extraction.pages:
        for span in page.spans:
            all_block_texts.append(span.text)

    # ── Step 2: Collect formula/table texts to protect from mangling ─────
    protected_texts: set[str] = set()
    for f in extraction.formulas:
        protected_texts.add(f.text)
    for t in extraction.tables:
        protected_texts.add(t.text)

    # ── Step 3: Normalize per-page, tracking new char offsets ────────────
    normalized_pages: list[NormalizedPage] = []
    all_headings: list[HeadingSpan] = []
    all_formulas: list[FormulaSpan] = []
    all_tables: list[TableSpan] = []
    full_parts: list[str] = []
    char_cursor = 0

    # Build a map from (source page, old char_start) → formula/table
    # so we can re-attach them with updated offsets.
    formula_map: dict[tuple[int, int], FormulaSpan] = {}
    for f in extraction.formulas:
        formula_map[(f.page, f.char_start)] = f

    table_map: dict[tuple[int, int], TableSpan] = {}
    for t in extraction.tables:
        table_map[(t.page, t.char_start)] = t

    for page in extraction.pages:
        page_spans: list[EvidenceSpan] = []
        page_text_parts: list[str] = []
        page_char_offset = char_cursor

        for span in page.spans:
            # Skip repeated headers/footers
            if _is_repeated_block(span.text, all_block_texts):
                continue

            # Clean the text — but protect formulas/tables
            if span.text in protected_texts:
                clean = span.text
            else:
                lines = span.text.splitlines()
                clean_lines = [_clean_line(l) for l in lines]
                clean = "\n".join(clean_lines)
                clean = _MULTI_NEWLINE.sub("\n\n", clean)
                clean = clean.strip()

            if not clean:
                continue

            new_start = char_cursor
            new_end = new_start + len(clean)

            new_span = EvidenceSpan(
                text=clean,
                source_id=span.source_id,
                page=span.page,
                char_start=new_start,
                char_end=new_end,
                bbox=span.bbox,
                paragraph_index=span.paragraph_index,
                heading_path=span.heading_path,
                confidence=span.confidence,
            )
            page_spans.append(new_span)

            # Re-attach formula if this span was one
            key = (span.page, span.char_start)
            if key in formula_map:
                orig = formula_map[key]
                all_formulas.append(
                    FormulaSpan(
                        text=clean,
                        source_id=orig.source_id,
                        page=orig.page,
                        char_start=new_start,
                        char_end=new_end,
                        bbox=orig.bbox,
                        latex=orig.latex,
                        variables=orig.variables,
                        result=orig.result,
                    )
                )

            if key in table_map:
                orig_t = table_map[key]
                all_tables.append(
                    TableSpan(
                        text=clean,
                        source_id=orig_t.source_id,
                        page=orig_t.page,
                        char_start=new_start,
                        char_end=new_end,
                        bbox=orig_t.bbox,
                        rows=orig_t.rows,
                        headers=orig_t.headers,
                        caption=orig_t.caption,
                    )
                )

            page_text_parts.append(clean)
            char_cursor = new_end + 1  # +1 for newline separator

        page_text = "\n".join(page_text_parts)
        full_parts.append(page_text)

        normalized_pages.append(
            NormalizedPage(
                page_number=page.page_number,
                text=page_text,
                char_offset=page_char_offset,
                spans=page_spans,
            )
        )

        # Re-map headings with updated offsets
        for heading in page.headings:
            # Find the span that corresponds to this heading
            for ns in page_spans:
                if heading.text.strip() in ns.text:
                    all_headings.append(
                        HeadingSpan(
                            text=heading.text,
                            level=heading.level,
                            page=heading.page,
                            char_start=ns.char_start,
                            char_end=ns.char_start + len(heading.text),
                        )
                    )
                    break
            else:
                # Heading text was removed (duplicate?) — skip
                pass

    full_text = "\n".join(full_parts)

    return NormalizedDocument(
        source_id=source_id,
        text=full_text,
        pages=normalized_pages,
        headings=all_headings,
        formulas=all_formulas,
        tables=all_tables,
    )
