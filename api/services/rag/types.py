"""RAG Pipeline types — evidence geometry flows through every phase.

The key insight: we track character positions and bounding boxes from extraction
through chunking through retrieval through citation. If any phase loses position
data, citations can't highlight the exact evidence.

Evidence geometry chain:
  Extract → EvidenceSpan (page, char_start, char_end, bbox)
  Normalize → preserves spans, updates char offsets
  Chunk → each chunk carries its spans
  Retrieve → matched chunks include spans
  Citation → answer claims bind to specific spans
  Deliver → UI draws highlight boxes from spans
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Evidence Geometry ────────────────────────────────────────────────────────

@dataclass
class BoundingBox:
    """Pixel-level box in the source document. Used for PDF highlight rendering."""
    x: float       # left edge (points from page left)
    y: float       # top edge (points from page top)
    width: float
    height: float
    page: int       # 0-indexed page number
    page_width: float = 595.0   # actual page width in points (default A4)
    page_height: float = 842.0  # actual page height in points (default A4)


@dataclass
class EvidenceSpan:
    """A span of text in the source document with precise location.
    This is the fundamental unit that makes citation highlighting work.
    """
    text: str                           # the exact text
    source_id: str                      # file/URL ID
    page: int = 0                       # 0-indexed page (or 0 for URLs)
    char_start: int = 0                 # character offset in extracted text
    char_end: int = 0                   # character end offset
    bbox: BoundingBox | None = None     # pixel-level highlight box (PDFs)
    paragraph_index: int = -1           # paragraph number (URLs)
    heading_path: list[str] = field(default_factory=list)  # e.g. ["Chapter 3", "3.2 Results"]
    confidence: float = 1.0             # how confident we are in the geometry


@dataclass
class FormulaSpan(EvidenceSpan):
    """A mathematical formula extracted from the document."""
    latex: str = ""                     # LaTeX representation
    variables: dict[str, str] = field(default_factory=dict)  # {"P": "pressure", "T": "temperature"}
    result: str = ""                    # computed result if applicable


@dataclass
class TableSpan(EvidenceSpan):
    """A table extracted from the document."""
    rows: list[list[str]] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    caption: str = ""


@dataclass
class FigureSpan(EvidenceSpan):
    """A figure/image extracted from the document."""
    image_data: str = ""                # base64 image
    caption: str = ""
    alt_text: str = ""


# ── Source Types ─────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    PDF = "pdf"
    URL = "url"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    TXT = "txt"
    IMAGE = "image"
    UNKNOWN = "unknown"


class ProcessingRoute(str, Enum):
    """How to process the source — decided by classify phase."""
    TEXT_NATIVE = "text_native"             # native text PDF, no OCR needed
    OCR_STANDARD = "ocr_standard"           # scanned PDF, standard OCR
    OCR_SCIENTIFIC = "ocr_scientific"       # equation-heavy, use Nougat/Docling
    HTML_STANDARD = "html_standard"         # web page
    OFFICE_STANDARD = "office_standard"     # Word/Excel/PowerPoint
    IMAGE_OCR = "image_ocr"                 # standalone image
    PLAINTEXT = "plaintext"                 # .txt, .md, .csv


class IngestionStatus(str, Enum):
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    QUEUED = "queued"
    CLASSIFYING = "classifying"
    EXTRACTING = "extracting"
    NORMALIZING = "normalizing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    PREPARING_CITATIONS = "preparing_citations"
    RAG_READY = "rag_ready"
    CITATION_READY = "citation_ready"
    FAILED = "failed"


class CoverageVerdict(str, Enum):
    SUFFICIENT = "sufficient"           # evidence fully answers the question
    PARTIAL = "partial"                 # some info found, gaps remain
    CONFLICTING = "conflicting"         # sources disagree
    INSUFFICIENT = "insufficient"       # not enough evidence
    MATH_READY = "math_ready"           # all formula inputs available
    MATH_INCOMPLETE = "math_incomplete" # missing variables for calculation


class CitationTier(str, Enum):
    EXACT = "exact"                     # precise bbox highlight
    PAGE = "page"                       # correct page, no exact position
    SNIPPET = "snippet"                 # text snippet match, no geometry
    FALLBACK = "fallback"               # best-effort location


# ── Phase Data Structures ────────────────────────────────────────────────────

@dataclass
class SourceRecord:
    """Created at upload time. Tracks the source through all phases."""
    id: str
    filename: str
    source_type: SourceType
    file_size: int = 0
    mime_type: str = ""
    group_id: str = ""                  # which group this belongs to
    owner_id: str = ""
    upload_url: str = ""                # storage URL / file path on disk
    status: IngestionStatus = IngestionStatus.UPLOADED
    processing_route: ProcessingRoute | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    # Readiness flags — set by specific phases only
    rag_ready: bool = False             # set by Phase 7 (Index) only
    citation_ready: bool = False        # set by Phase 8 (Citation Prep) only

    # Tier / lifecycle fields
    scope: str = "user_temp"            # "library" | "user_temp"
    flagged: bool = False               # user submitted for admin review
    flagged_at: str | None = None       # ISO timestamp when flagged
    expires_at: str | None = None       # ISO timestamp for auto-deletion (None = never)
    flag_note: str = ""                 # optional note from the user when flagging


@dataclass
class ClassificationResult:
    """Output of Phase 2: Classify."""
    source_id: str
    source_type: SourceType
    processing_route: ProcessingRoute
    has_images: bool = False
    has_tables: bool = False
    has_formulas: bool = False
    has_scanned_pages: bool = False
    page_count: int = 0
    language: str = "en"
    confidence: float = 1.0


@dataclass
class ExtractionResult:
    """Output of Phase 3: Extract. Carries raw text + evidence geometry."""
    source_id: str
    pages: list[PageExtraction] = field(default_factory=list)
    formulas: list[FormulaSpan] = field(default_factory=list)
    tables: list[TableSpan] = field(default_factory=list)
    figures: list[FigureSpan] = field(default_factory=list)
    full_text: str = ""                 # concatenated text for convenience
    extraction_method: str = ""         # "native_text" | "paddle_ocr" | "docling" | "nougat"
    warnings: list[str] = field(default_factory=list)


@dataclass
class PageExtraction:
    """Extracted content from a single page."""
    page_number: int                    # 0-indexed
    text: str
    headings: list[HeadingSpan] = field(default_factory=list)
    spans: list[EvidenceSpan] = field(default_factory=list)  # all text spans with geometry
    formulas: list[FormulaSpan] = field(default_factory=list)
    tables: list[TableSpan] = field(default_factory=list)
    figures: list[FigureSpan] = field(default_factory=list)
    char_offset: int = 0               # offset in full_text


@dataclass
class HeadingSpan:
    """A heading in the document."""
    text: str
    level: int                          # 1=h1, 2=h2, etc
    page: int
    char_start: int = 0
    char_end: int = 0


@dataclass
class NormalizedDocument:
    """Output of Phase 4: Normalize. Clean text with preserved geometry."""
    source_id: str
    text: str                           # canonical cleaned text
    pages: list[NormalizedPage] = field(default_factory=list)
    headings: list[HeadingSpan] = field(default_factory=list)
    formulas: list[FormulaSpan] = field(default_factory=list)
    tables: list[TableSpan] = field(default_factory=list)


@dataclass
class NormalizedPage:
    """Normalized content from a single page."""
    page_number: int
    text: str
    char_offset: int                    # offset in full normalized text
    spans: list[EvidenceSpan] = field(default_factory=list)


@dataclass
class Chunk:
    """Output of Phase 5: Chunk. A retrieval unit with full provenance."""
    id: str
    source_id: str
    text: str
    page_start: int                     # first page this chunk covers
    page_end: int                       # last page
    char_start: int                     # char offset in normalized text
    char_end: int
    heading_path: list[str] = field(default_factory=list)
    spans: list[EvidenceSpan] = field(default_factory=list)  # exact text positions
    formulas: list[FormulaSpan] = field(default_factory=list)
    tables: list[TableSpan] = field(default_factory=list)
    chunk_type: str = "text"            # "text" | "table" | "formula" | "figure"
    metadata: dict[str, Any] = field(default_factory=dict)

    # Group metadata for filtered retrieval
    group_id: str = ""
    owner_id: str = ""
    filename: str = ""
    source_type: str = ""


@dataclass
class EmbeddedChunk(Chunk):
    """Output of Phase 6: Embed. Chunk with vector."""
    embedding: list[float] = field(default_factory=list)
    embedding_model: str = ""
    embedding_version: str = ""


@dataclass
class IndexedChunk(EmbeddedChunk):
    """Output of Phase 7: Index. Chunk stored in vector DB."""
    index_id: str = ""
    indexed_at: str = ""


@dataclass
class CitationAnchor:
    """Output of Phase 8: Citation Prep. A precise jump target."""
    source_id: str
    chunk_id: str
    page: int
    tier: CitationTier = CitationTier.SNIPPET
    bbox: BoundingBox | None = None     # exact highlight box (tier=EXACT)
    text_snippet: str = ""              # fallback text to match
    paragraph_index: int = -1           # for URL citations
    heading_path: list[str] = field(default_factory=list)
    url_fragment: str = ""              # #section-id for URL jumps


@dataclass
class RetrievedEvidence:
    """Output of Phase 9: Retrieve. A chunk matched to a query."""
    chunk: Chunk
    score: float                        # retrieval similarity score
    match_type: str = "vector"          # "vector" | "keyword" | "hybrid"
    anchors: list[CitationAnchor] = field(default_factory=list)


@dataclass
class RankedEvidence(RetrievedEvidence):
    """Output of Phase 10: Rerank. Evidence with final relevance score."""
    rerank_score: float = 0.0
    credibility_score: float = 0.0
    diversity_bonus: float = 0.0
    final_score: float = 0.0


@dataclass
class CoverageResult:
    """Output of Phase 11: Coverage Check."""
    verdict: CoverageVerdict
    answered_aspects: list[str] = field(default_factory=list)
    missing_aspects: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    math_variables: dict[str, str] = field(default_factory=dict)   # found variables
    math_missing: list[str] = field(default_factory=list)           # missing variables
    confidence: float = 0.0


@dataclass
class AnswerClaim:
    """A single claim in the generated answer, bound to evidence."""
    text: str                           # the claim text in the answer
    evidence: list[RankedEvidence] = field(default_factory=list)
    anchors: list[CitationAnchor] = field(default_factory=list)
    ref_ids: list[str] = field(default_factory=list)  # [1], [2], etc
    is_calculation: bool = False
    calculation_trace: str = ""         # "P = nRT/V = (2)(8.314)(300)/(0.1) = 49884 Pa"


@dataclass
class GeneratedAnswer:
    """Output of Phase 12: Answer."""
    text: str                           # full answer with [ref] markers
    claims: list[AnswerClaim] = field(default_factory=list)
    coverage: CoverageResult | None = None
    grounded: bool = True               # false if answer includes non-evidence info
    has_calculations: bool = False
    highlight_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    # highlight_map: {"1": {"quote": "exact words", "page": 1}, ...}


@dataclass
class Citation:
    """Output of Phase 13: Citations. A renderable citation reference."""
    ref_id: str                         # "[1]", "[2]", etc
    source_id: str
    source_name: str                    # filename or URL title
    source_type: SourceType
    page: int
    tier: CitationTier
    snippet: str                        # text that was cited
    anchor: CitationAnchor | None = None  # jump target with highlight box

    # For PDF citations
    highlight_boxes: list[BoundingBox] = field(default_factory=list)

    # For URL citations
    url: str = ""
    url_fragment: str = ""              # #section-id
    paragraph_index: int = -1

    # Metadata
    credibility: str = ""               # "high" | "medium" | "low"
    relevance_score: float = 0.0


@dataclass
class DeliveryPayload:
    """Output of Phase 14: Deliver. Everything the UI needs."""
    answer: GeneratedAnswer
    citations: list[Citation] = field(default_factory=list)
    evidence_panel: list[EvidenceCard] = field(default_factory=list)
    search_scope: str = ""              # "group:marketing_docs" | "file:report.pdf"
    warnings: list[str] = field(default_factory=list)
    trace_id: str = ""


@dataclass
class EvidenceCard:
    """A card in the evidence panel showing source + highlighted text."""
    source_id: str
    source_name: str
    source_type: SourceType
    page: int
    snippet: str
    relevance_score: float
    highlight_boxes: list[BoundingBox] = field(default_factory=list)
    heading_path: list[str] = field(default_factory=list)
    ref_id: str = ""                    # which citation this supports


# ── Pipeline Configuration ───────────────────────────────────────────────────

@dataclass
class RAGConfig:
    """Pipeline-wide configuration. No artificial limits — developer decides everything."""
    # Embedding
    embedding_model: str = ""           # developer sets via env or config
    embedding_dimensions: int = 0       # 0 = auto-detect from model

    # Chunking
    chunk_size: int = 0                 # 0 = no limit, use structure-aware splitting only
    chunk_overlap: int = 0              # 0 = no overlap
    preserve_formulas: bool = True      # never split formulas
    preserve_tables: bool = True        # never split tables

    # Retrieval
    top_k: int = 0                      # 0 = return all matches
    final_k: int = 0                    # 0 = return all after rerank
    hybrid_weight: float = 0.7          # vector vs keyword (0=keyword, 1=vector)

    # Reranking
    rerank_model: str = ""              # empty = scoring-based, no model
    credibility_weight: float = 0.2
    diversity_weight: float = 0.1

    # Answer
    answer_model: str = ""              # cheap model for general questions (gpt-4o-mini)
    math_model: str = ""                # reasoning model for math/calculation (o4-mini)
    vision_model: str = ""              # vision model for image descriptions (gpt-4o-mini)
    classify_model: str = ""            # model for question classification (gpt-4o-mini)
    max_answer_tokens: int = 0          # 0 = no limit, model decides
    allow_calculations: bool = True
    grounding_mode: str = "strict"      # "strict" = evidence only, "relaxed" = allow general knowledge

    # Citations
    citation_mode: str = "inline"       # "inline" | "footnote"
    highlight_enabled: bool = True
    fallback_to_page: bool = True       # if no exact geometry, cite the page

    # Observability
    trace_enabled: bool = True


# ── Stage Events for Observability ───────────────────────────────────────────

@dataclass
class StageEvent:
    """Emitted by each phase for observability."""
    trace_id: str
    stage: str                          # "upload" | "classify" | "extract" | etc
    source_id: str
    status: str                         # "started" | "completed" | "failed"
    detail: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
