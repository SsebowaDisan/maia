"""RAG Pipeline Phase 2: Classify — detect source type & choose processing route."""

from __future__ import annotations

import os
import re

from api.services.rag.types import (
    ClassificationResult,
    ProcessingRoute,
    SourceRecord,
    SourceType,
)

# ── Math / equation heuristics ──────────────────────────────────────────────

_LATEX_MARKERS = re.compile(
    r"\\(?:frac|sqrt|int|sum|prod|lim|begin\{equation\}|begin\{align\}|"
    r"alpha|beta|gamma|delta|epsilon|theta|lambda|sigma|omega|partial|nabla|infty)",
)

_MATH_UNICODE = re.compile(
    r"[\u2200-\u22FF\u2A00-\u2AFF\u00B1\u00D7\u00F7\u2260\u2264\u2265\u221E]"
)


def _has_equations(text: str) -> bool:
    """Return True if text is equation-heavy (>= 5 LaTeX markers or math symbols per 1000 chars)."""
    if not text:
        return False
    latex_count = len(_LATEX_MARKERS.findall(text))
    math_count = len(_MATH_UNICODE.findall(text))
    density = (latex_count + math_count) / max(len(text) / 1000, 1)
    return density >= 5


def _has_tables(text: str) -> bool:
    """Heuristic: detect tabular content (pipe-delimited rows or repeated tab columns)."""
    pipe_rows = sum(1 for line in text.splitlines() if line.count("|") >= 3)
    tab_rows = sum(1 for line in text.splitlines() if line.count("\t") >= 2)
    return pipe_rows >= 3 or tab_rows >= 3


# ── PDF helpers ─────────────────────────────────────────────────────────────


def _pdf_first_page_text(file_data: bytes) -> str:
    """Extract text from the first page of a PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=file_data, filetype="pdf")
        if doc.page_count == 0:
            return ""
        page = doc[0]
        text = page.get_text("text")
        doc.close()
        return text
    except Exception:
        return ""


def _pdf_page_count(file_data: bytes) -> int:
    try:
        import fitz

        doc = fitz.open(stream=file_data, filetype="pdf")
        count = doc.page_count
        doc.close()
        return count
    except Exception:
        return 0


# ── Extension to SourceType mapping (mirrors upload.py) ────────────────────

_EXT_MAP: dict[str, SourceType] = {
    ".pdf": SourceType.PDF,
    ".docx": SourceType.DOCX,
    ".doc": SourceType.DOCX,
    ".xlsx": SourceType.XLSX,
    ".xls": SourceType.XLSX,
    ".pptx": SourceType.PPTX,
    ".ppt": SourceType.PPTX,
    ".txt": SourceType.TXT,
    ".md": SourceType.TXT,
    ".csv": SourceType.TXT,
    ".tsv": SourceType.TXT,
    ".json": SourceType.TXT,
    ".png": SourceType.IMAGE,
    ".jpg": SourceType.IMAGE,
    ".jpeg": SourceType.IMAGE,
    ".gif": SourceType.IMAGE,
    ".bmp": SourceType.IMAGE,
    ".tiff": SourceType.IMAGE,
    ".tif": SourceType.IMAGE,
    ".webp": SourceType.IMAGE,
    ".svg": SourceType.IMAGE,
}


# ── Public API ──────────────────────────────────────────────────────────────


async def classify_source(
    source: SourceRecord,
    file_data: bytes | None = None,
) -> ClassificationResult:
    """Classify a source and choose its processing route.

    For PDFs this inspects the first page to decide between native text,
    standard OCR, or scientific OCR routes.
    """
    source_type = source.source_type
    ext = os.path.splitext(source.filename)[1].lower()

    # Override source_type from extension if it was UNKNOWN
    if source_type == SourceType.UNKNOWN:
        source_type = _EXT_MAP.get(ext, SourceType.UNKNOWN)

    has_formulas = False
    has_tables = False
    has_scanned = False
    has_images = False
    page_count = 0
    route = ProcessingRoute.PLAINTEXT  # default

    # ── URL ──────────────────────────────────────────────────────────────
    if source_type == SourceType.URL:
        route = ProcessingRoute.HTML_STANDARD

    # ── PDF ──────────────────────────────────────────────────────────────
    elif source_type == SourceType.PDF:
        all_text = ""
        page_count = 0
        if file_data:
            try:
                import fitz
                doc = fitz.open(stream=file_data, filetype="pdf")
                page_count = doc.page_count
                # Check first 5 pages for text (not just first — title pages are often sparse)
                page_texts = []
                for i in range(min(5, doc.page_count)):
                    page_texts.append(doc[i].get_text("text"))
                all_text = "\n".join(page_texts)
                doc.close()
            except Exception:
                pass

        total_chars = len(all_text.strip())
        # Scanned = very little text across multiple pages
        has_scanned = total_chars < 100 and page_count > 0

        if has_scanned:
            route = ProcessingRoute.OCR_STANDARD
        else:
            has_formulas = _has_equations(all_text)
            has_tables = _has_tables(all_text)

            if has_formulas:
                route = ProcessingRoute.OCR_SCIENTIFIC
            else:
                route = ProcessingRoute.TEXT_NATIVE

    # ── Office docs ─────────────────────────────────────────────────────
    elif source_type in (SourceType.DOCX, SourceType.XLSX, SourceType.PPTX):
        route = ProcessingRoute.OFFICE_STANDARD

    # ── Images ──────────────────────────────────────────────────────────
    elif source_type == SourceType.IMAGE:
        route = ProcessingRoute.IMAGE_OCR
        has_images = True

    # ── Plain text family ───────────────────────────────────────────────
    elif source_type == SourceType.TXT:
        route = ProcessingRoute.PLAINTEXT

    return ClassificationResult(
        source_id=source.id,
        source_type=source_type,
        processing_route=route,
        has_images=has_images,
        has_tables=has_tables,
        has_formulas=has_formulas,
        has_scanned_pages=has_scanned,
        page_count=page_count,
        language="en",
        confidence=0.9 if file_data else 0.7,
    )
