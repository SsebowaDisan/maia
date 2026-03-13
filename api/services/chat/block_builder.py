"""Structured block builder — single source of truth for chat turn blocks.

Converts a plain answer text + optional context (question, workspace IDs) into a
typed ``list[MessageBlock]`` + ``list[CanvasDocumentRecord]`` that passes through
``normalize_turn_structured_content`` before being returned.

Rules applied, in order
-----------------------
1. If the question matches an optics / thin-lens pattern, prepend a
   ``widget:lens_equation`` block with extracted or default parameters.
2. Segment the answer text into typed blocks:
   - Fenced code  (``` ... ```)     → ``code`` block
   - Display math ($$...$$)         → ``math`` block (display=True)
   - Markdown table  (| … | rows)   → ``table`` block
   - Remaining prose                → ``markdown`` block
3. For each workspace document captured by the orchestrator, append a
   ``document_action`` block and a matching ``CanvasDocumentRecord``.
4. Always emit at least one valid block (fallback: single markdown block).

Usage
-----
    from api.services.chat.block_builder import build_turn_blocks

    blocks, documents = build_turn_blocks(
        answer_text=answer,
        question=message,
        workspace_ids=captured_workspace_ids,   # optional
    )
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from api.message_blocks import normalize_turn_structured_content

# ---------------------------------------------------------------------------
# Optics / thin-lens detection
# ---------------------------------------------------------------------------

_OPTICS_KEYWORDS = re.compile(
    r"\b("
    r"thin\s+lens|lens\s+equation|focal\s+length|object\s+distance|image\s+distance"
    r"|converging\s+lens|diverging\s+lens|magnification"
    r"|1\s*/\s*f|diopter|optic(?:al)?\s+system"
    r")\b",
    re.IGNORECASE,
)

_FOCAL_LENGTH_RE = re.compile(
    r"(?:focal\s+length|f)\s*[=:≈]\s*([\-\d]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_OBJECT_DIST_RE = re.compile(
    r"(?:object\s+distance|u|d[_\s]?o)\s*[=:≈]\s*([\-\d]+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _is_optics_question(question: str) -> bool:
    return bool(_OPTICS_KEYWORDS.search(question))


def _extract_lens_props(answer_text: str, question: str) -> dict[str, Any]:
    combined = f"{question}\n{answer_text}"
    fl = _FOCAL_LENGTH_RE.search(combined)
    od = _OBJECT_DIST_RE.search(combined)
    return {
        "focalLength": float(fl.group(1)) if fl else 10.0,
        "objectDistance": float(od.group(1)) if od else 30.0,
    }


# ---------------------------------------------------------------------------
# Answer text segmentation
# ---------------------------------------------------------------------------

# Combined regex: fenced code blocks first, then display math.
_SEGMENT_RE = re.compile(
    r"```(?P<lang>[^\n]*)\n(?P<code>.*?)```"   # fenced code
    r"|\$\$(?P<math>[^$]+)\$\$",               # display math  (no nested $$)
    re.DOTALL,
)

# A "table line": starts with | (ignoring leading whitespace).
_TABLE_LINE_RE = re.compile(r"^\s*\|.+\|", re.MULTILINE)


def _parse_table_lines(lines: list[str]) -> dict[str, Any] | None:
    """Parse consecutive pipe-delimited lines into a TableBlock dict."""
    if len(lines) < 2:
        return None
    raw_cols = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    data_lines = [l for l in lines[2:] if "|" in l]
    rows: list[list[str]] = []
    for dl in data_lines:
        cells = [c.strip() for c in dl.strip().strip("|").split("|")]
        # Pad / trim to column count.
        while len(cells) < len(raw_cols):
            cells.append("")
        rows.append(cells[: len(raw_cols)])
    if not raw_cols:
        return None
    return {"type": "table", "columns": raw_cols, "rows": rows}


def _prose_to_blocks(prose: str) -> list[dict[str, Any]]:
    """Convert a plain-prose segment into block(s).

    Extracts standalone markdown tables; everything else becomes a
    single ``markdown`` block.
    """
    if not prose.strip():
        return []
    blocks: list[dict[str, Any]] = []
    lines = prose.split("\n")
    pending: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*\|.+\|", line):
            # Flush pending prose.
            txt = "\n".join(pending).strip()
            if txt:
                blocks.append({"type": "markdown", "markdown": txt})
            pending = []
            # Collect all consecutive table lines.
            table_lines: list[str] = []
            while i < len(lines) and re.match(r"^\s*\|", lines[i]):
                table_lines.append(lines[i])
                i += 1
            tbl = _parse_table_lines(table_lines)
            if tbl:
                blocks.append(tbl)
            else:
                # Fallback: keep as markdown.
                blocks.append({"type": "markdown", "markdown": "\n".join(table_lines)})
        else:
            pending.append(line)
            i += 1

    txt = "\n".join(pending).strip()
    if txt:
        blocks.append({"type": "markdown", "markdown": txt})
    return blocks


def _segment_answer(answer_text: str) -> list[dict[str, Any]]:
    """Segment ``answer_text`` into typed block dicts.

    Extraction priority: fenced code > display math > markdown tables > prose.
    """
    if not answer_text.strip():
        return []

    blocks: list[dict[str, Any]] = []
    last_end = 0

    for m in _SEGMENT_RE.finditer(answer_text):
        start, end = m.span()
        # Prose/table segment before this match.
        if start > last_end:
            blocks.extend(_prose_to_blocks(answer_text[last_end:start]))

        if m.group("code") is not None:
            lang = (m.group("lang") or "").strip()
            code = m.group("code")
            blocks.append({"type": "code", "language": lang, "code": code})
        elif m.group("math") is not None:
            latex = m.group("math").strip()
            if latex:
                blocks.append({"type": "math", "latex": latex, "display": True})

        last_end = end

    # Trailing segment.
    if last_end < len(answer_text):
        blocks.extend(_prose_to_blocks(answer_text[last_end:]))

    return blocks or [{"type": "markdown", "markdown": answer_text}]


# ---------------------------------------------------------------------------
# Document action helpers
# ---------------------------------------------------------------------------

def _doc_action_blocks(
    workspace_ids: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Emit ``document_action`` + ``CanvasDocumentRecord`` pairs for workspace docs."""
    blocks: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []

    pairs = [
        (
            workspace_ids.get("deep_research_doc_id") or "",
            workspace_ids.get("deep_research_doc_url") or "",
            "Research Document",
        ),
        (
            workspace_ids.get("deep_research_sheet_id") or "",
            workspace_ids.get("deep_research_sheet_url") or "",
            "Research Spreadsheet",
        ),
    ]
    for doc_id, doc_url, title in pairs:
        if not (doc_id or doc_url):
            continue
        stable_id = doc_id or f"ws_{uuid.uuid4().hex[:8]}"
        blocks.append(
            {
                "type": "document_action",
                "action": {
                    "kind": "open_canvas",
                    "title": title,
                    "documentId": stable_id,
                },
            }
        )
        documents.append({"id": stable_id, "title": title, "content": doc_url})

    return blocks, documents


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_turn_blocks(
    *,
    answer_text: str,
    question: str = "",
    workspace_ids: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build validated blocks + documents for one conversation turn.

    Parameters
    ----------
    answer_text:
        The final assistant answer (may contain markdown, code fences,
        display math, or pipe tables).
    question:
        The user's question — used for widget-trigger detection.
    workspace_ids:
        Optional mapping of ``deep_research_{doc,sheet}_{id,url}`` keys
        from the orchestrator's captured workspace state.  When provided,
        emits ``document_action`` blocks so the canvas opens automatically.

    Returns
    -------
    (blocks, documents) — both already validated through
    ``normalize_turn_structured_content``.  Always at least one block.
    """
    raw_blocks: list[dict[str, Any]] = []
    raw_documents: list[dict[str, Any]] = []

    # 1. Lens widget — prepended so it appears above the answer text.
    if question and _is_optics_question(question):
        props = _extract_lens_props(answer_text, question)
        raw_blocks.append(
            {"type": "widget", "widget": {"kind": "lens_equation", "props": props}}
        )

    # 2. Structured answer segmentation.
    raw_blocks.extend(_segment_answer(answer_text))

    # 3. Document actions from orchestrator workspace.
    if workspace_ids:
        doc_blocks, doc_records = _doc_action_blocks(workspace_ids)
        raw_blocks.extend(doc_blocks)
        raw_documents.extend(doc_records)

    # 4. Validate through the canonical schema — falls back to markdown on failure.
    return normalize_turn_structured_content(
        answer_text=answer_text,
        blocks=raw_blocks or None,
        documents=raw_documents or None,
    )
