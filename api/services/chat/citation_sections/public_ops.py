from __future__ import annotations

import re

from .anchors import _anchors_to_bracket_markers
from .cleanup import (
    _dedupe_duplicate_answer_passes,
    _format_notebook_style_layout,
    _strip_fast_qa_noise_sections,
)
from .injection import _inject_inline_citations, render_fast_citation_links
from .refs import resolve_required_citation_mode
from .resolution import _resolve_citation_refs

# Agent answers already contain structured markdown citation sections built by
# answer_builder_sections/citations.py.  Running the Fast QA HTML-injection
# pipeline on top of these corrupts the output: sequence numbers like [1] in
# "- [1] [Label](url)" bullets get replaced with raw <a class='citation'>
# anchors, and inline URL bullets in ## Executive Summary gain unwanted HTML.
_AGENT_CITATION_SECTION_RE = re.compile(
    r"^##\s+(?:Evidence Citations|Sources|References)\s*$",
    re.MULTILINE,
)


def enforce_required_citations(
    *,
    answer: str,
    info_html: str,
    citation_mode: str | None,
) -> str:
    text = (answer or "").strip()
    if not text:
        return text

    # Agent-format answers already have clean citation sections — skip injection.
    if _AGENT_CITATION_SECTION_RE.search(text):
        return text

    mode = resolve_required_citation_mode(citation_mode)
    refs = _resolve_citation_refs(info_html=info_html, answer=text)
    layout_seed = text
    if "class='citation'" in layout_seed or 'class="citation"' in layout_seed:
        layout_seed = _anchors_to_bracket_markers(layout_seed)
    layout_seed = _format_notebook_style_layout(layout_seed)
    enriched = render_fast_citation_links(answer=layout_seed, refs=refs, citation_mode=mode)
    enriched = _inject_inline_citations(enriched, refs)
    if "class='citation'" in enriched or 'class="citation"' in enriched:
        return _dedupe_duplicate_answer_passes(enriched)
    if refs:
        return _dedupe_duplicate_answer_passes(enriched)
    return (
        f"{enriched}\n\n"
        "Evidence: internal execution trace (no external source references were returned by the retrieval pipeline)."
    )


def append_required_citation_suffix(*, answer: str, info_html: str) -> str:
    raw_text = str(answer or "")
    if not raw_text.strip():
        return ""

    refs = _resolve_citation_refs(info_html=info_html, answer=raw_text)
    if refs:
        layout_seed = raw_text
        if "class='citation'" in layout_seed or 'class="citation"' in layout_seed:
            layout_seed = _anchors_to_bracket_markers(layout_seed)
        layout_seed = _format_notebook_style_layout(layout_seed)
        enriched = render_fast_citation_links(
            answer=layout_seed,
            refs=refs,
            citation_mode="inline",
        )
        enriched = _inject_inline_citations(enriched, refs)
        from .visible import _normalize_visible_inline_citations

        enriched = _normalize_visible_inline_citations(enriched)
        enriched = _dedupe_duplicate_answer_passes(enriched)
        if "class='citation'" in enriched or 'class="citation"' in enriched:
            return enriched
        from .anchors import _citation_anchor

        fallback_refs = " ".join([_citation_anchor(ref) for ref in refs[: min(3, len(refs))] if _citation_anchor(ref)])
        return f"{enriched}\n\nEvidence: {fallback_refs}"
    if "class='citation'" in raw_text or 'class="citation"' in raw_text:
        from .visible import _normalize_visible_inline_citations

        return _dedupe_duplicate_answer_passes(_normalize_visible_inline_citations(raw_text))
    return (
        f"{raw_text}\n\n"
        "Evidence: internal execution trace (no external source references were returned by the retrieval pipeline)."
    )


def normalize_fast_answer(answer: str, *, question: str = "") -> str:
    text = (answer or "").strip()
    if not text:
        return ""

    text = re.sub(r"(?<!\n)(#{2,6}\s+)", r"\n\n\1", text)
    text = re.sub(r"(^|\n)\s*#{1,6}\s*#{1,6}\s*", r"\1## ", text)
    text = _strip_fast_qa_noise_sections(text, question=question)

    malformed_bold = bool(re.search(r"#{2,6}\s*\*\*|\*\*[^*]+-\s*\*\*", text))
    if malformed_bold or text.count("**") % 2 == 1:
        text = text.replace("**", "")

    blocks = [row.strip() for row in text.split("\n\n")]
    deduped_blocks: list[str] = []
    seen_signatures: set[str] = set()
    for block in blocks:
        if not block:
            continue
        signature = re.sub(r"(?:\[|【|ã€|\{)\s*\d{1,4}\s*(?:\]|】|ã€‘|\})", "", block)
        signature = re.sub(r"\s+", " ", signature).strip().lower()
        if len(signature) >= 120 and signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        deduped_blocks.append(block)
    text = "\n\n".join(deduped_blocks)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
