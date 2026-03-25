from __future__ import annotations

import re

from api.services.observability.citation_trace import record_trace_event

from .anchors import _anchors_to_bracket_markers, _augment_existing_citation_anchors
from .cleanup import (
    _dedupe_duplicate_answer_passes,
    _format_notebook_style_layout,
    _strip_fast_qa_noise_sections,
)
from .injection import (
    _diversify_repeated_ref_numbers,
    _enforce_paragraph_citation_coverage,
    _guard_citation_dominance,
    _inject_claim_level_bracket_citations,
    _inject_inline_citations,
    _realign_bracket_ref_numbers,
    render_fast_citation_links,
)
from .refs import resolve_required_citation_mode
from .resolution import _extract_info_refs, _extract_refs_from_answer_citation_section, _resolve_citation_refs

# Agent answers already contain structured markdown citation sections built by
# answer_builder_sections/citations.py.  Running the Fast QA HTML-injection
# pipeline on top of these corrupts the output: sequence numbers like [1] in
# "- [1] [Label](url)" bullets get replaced with raw <a class='citation'>
# anchors, and inline URL bullets in ## Executive Summary gain unwanted HTML.
_AGENT_CITATION_SECTION_RE = re.compile(
    r"^##\s+(?:Evidence Citations|Sources|References)\s*$",
    re.MULTILINE,
)
_RAW_PAGE_PROSE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b[Pp]age\s+\d{1,4}\s+(?=(?:explicitly\s+)?(?:identifies|states|notes|shows|confirms|indicates|documents|reports|describes|prescribes)\b)"
        ),
        "The cited source ",
    ),
    (
        re.compile(
            r"\b(?:on|from)\s+[Pp]age\s+\d{1,4}\b",
        ),
        "in the cited source",
    ),
    (
        re.compile(
            r"\bper\s+[Pp]age\s+\d{1,4}(?:'s)?\b",
        ),
        "in the cited source",
    ),
)


def _normalize_explicit_page_prose(text: str) -> str:
    value = str(text or "")
    if not value:
        return value
    normalized = value
    for pattern, replacement in _RAW_PAGE_PROSE_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    normalized = re.sub(r"\bin the cited source's\b", "in the cited source", normalized, flags=re.IGNORECASE)
    return normalized


def _repair_marker_level_citations(text: str, refs: list[dict]) -> str:
    repaired = str(text or "")
    if not repaired or not refs:
        return repaired
    repaired = _realign_bracket_ref_numbers(repaired, refs)
    repaired = _diversify_repeated_ref_numbers(repaired, refs)
    repaired = _enforce_paragraph_citation_coverage(repaired, refs)
    repaired = _guard_citation_dominance(repaired, refs)
    repaired = _inject_claim_level_bracket_citations(repaired, refs)
    return repaired


def enforce_required_citations(
    *,
    answer: str,
    info_html: str,
    citation_mode: str | None,
) -> str:
    text = (answer or "").strip()
    if not text:
        return text
    record_trace_event(
        "citation.enforce_started",
        {
            "answer_length": len(text),
            "citation_mode": str(citation_mode or ""),
            "has_info_html": bool(str(info_html or "").strip()),
        },
    )

    # Agent-format answers have a structured ## Evidence Citations tail.
    # Inject anchors into the body only; preserve the citation section unchanged.
    agent_match = _AGENT_CITATION_SECTION_RE.search(text)
    if agent_match:
        body = text[: agent_match.start()].rstrip()
        tail = text[agent_match.start() :]
        # Use the answer's citation section as the CANONICAL ref list (sequential
        # IDs 1, 2, 3 … matching the ## Evidence Citations bullets).  Enrich each
        # ref with highlight/strength metadata from the info_html panel by URL.
        refs = _extract_refs_from_answer_citation_section(text)
        if not refs:
            return text
        info_refs = _extract_info_refs(info_html) if info_html else []
        if info_refs:
            info_by_id: dict[int, dict] = {}
            info_by_url: dict[str, dict] = {}
            for iref in info_refs:
                ref_id = int(iref.get("id", 0) or 0)
                if ref_id > 0 and ref_id not in info_by_id:
                    info_by_id[ref_id] = iref
                url_key = str(iref.get("source_url") or "").strip().lower().rstrip("/")
                if url_key and url_key not in info_by_url:
                    info_by_url[url_key] = iref
            for ref in refs:
                ref_id = int(ref.get("id", 0) or 0)
                iref = info_by_id.get(ref_id)
                if iref is None:
                    url_key = str(ref.get("source_url") or "").strip().lower().rstrip("/")
                    if url_key and url_key in info_by_url:
                        iref = info_by_url[url_key]
                if iref is None:
                    continue
                for key in (
                    "phrase",
                    "highlight_boxes",
                    "evidence_units",
                    "unit_id",
                    "match_quality",
                    "strength_score",
                    "char_start",
                    "char_end",
                    "source_id",
                    "source_url",
                    "page_label",
                    "source_name",
                    "label",
                ):
                    if not ref.get(key) and iref.get(key):
                        ref[key] = iref[key]
        mode = resolve_required_citation_mode(citation_mode)
        repaired_body = _repair_marker_level_citations(body, refs)
        enriched_body = render_fast_citation_links(answer=repaired_body, refs=refs, citation_mode=mode)
        enriched_body = _inject_inline_citations(enriched_body, refs)
        enriched_body = _normalize_explicit_page_prose(enriched_body)
        enriched_body = _dedupe_duplicate_answer_passes(enriched_body)
        record_trace_event(
            "citation.enforce_completed",
            {
                "ref_count": len(refs),
                "path": "agent_section",
                "answer_length": len(enriched_body),
            },
        )
        return f"{enriched_body.rstrip()}\n\n{tail.lstrip()}"

    # If inline citation anchors already exist (placed by render_fast_citation_links),
    # only augment them with metadata from info_html — do not strip and reinject.
    if "class='citation'" in text or 'class="citation"' in text:
        refs = _resolve_citation_refs(info_html=info_html, answer=text)
        if not refs:
            return _dedupe_duplicate_answer_passes(text)
        mode = resolve_required_citation_mode(citation_mode)
        marker_text = _anchors_to_bracket_markers(_augment_existing_citation_anchors(text, refs))
        marker_text = _format_notebook_style_layout(marker_text)
        marker_text = _repair_marker_level_citations(marker_text, refs)
        enriched = render_fast_citation_links(answer=marker_text, refs=refs, citation_mode=mode)
        enriched = _inject_inline_citations(enriched, refs)
        enriched = _normalize_explicit_page_prose(enriched)
        record_trace_event(
            "citation.enforce_completed",
            {
                "ref_count": len(refs),
                "path": "existing_anchors",
                "answer_length": len(enriched),
            },
        )
        return _dedupe_duplicate_answer_passes(enriched)

    mode = resolve_required_citation_mode(citation_mode)
    refs = _resolve_citation_refs(info_html=info_html, answer=text)
    layout_seed = _format_notebook_style_layout(text)
    layout_seed = _repair_marker_level_citations(layout_seed, refs)
    enriched = render_fast_citation_links(answer=layout_seed, refs=refs, citation_mode=mode)
    enriched = _inject_inline_citations(enriched, refs)
    enriched = _normalize_explicit_page_prose(enriched)
    if "class='citation'" in enriched or 'class="citation"' in enriched:
        record_trace_event(
            "citation.enforce_completed",
            {
                "ref_count": len(refs),
                "path": "fresh_render",
                "answer_length": len(enriched),
            },
        )
        return _dedupe_duplicate_answer_passes(enriched)
    if refs:
        record_trace_event(
            "citation.enforce_completed",
            {
                "ref_count": len(refs),
                "path": "fresh_render_no_anchor_class",
                "answer_length": len(enriched),
            },
        )
        return _dedupe_duplicate_answer_passes(enriched)
    record_trace_event(
        "citation.enforce_completed",
        {
            "ref_count": 0,
            "path": "no_refs_passthrough",
            "answer_length": len(enriched),
        },
    )
    return _dedupe_duplicate_answer_passes(enriched)


def append_required_citation_suffix(*, answer: str, info_html: str) -> str:
    raw_text = str(answer or "")
    if not raw_text.strip():
        return ""

    # Agent-format answers have a structured ## Evidence Citations tail.
    # Inject anchors into the body only; preserve the citation section unchanged.
    agent_match = _AGENT_CITATION_SECTION_RE.search(raw_text)
    if agent_match:
        body = raw_text[: agent_match.start()].rstrip()
        tail = raw_text[agent_match.start() :]
        # Same as enforce_required_citations: answer section refs are canonical.
        refs = _extract_refs_from_answer_citation_section(raw_text)
        if not refs:
            return raw_text
        info_refs = _extract_info_refs(info_html) if info_html else []
        if info_refs:
            info_by_url: dict[str, dict] = {}
            for iref in info_refs:
                url_key = str(iref.get("source_url") or "").strip().lower().rstrip("/")
                if url_key and url_key not in info_by_url:
                    info_by_url[url_key] = iref
            for ref in refs:
                url_key = str(ref.get("source_url") or "").strip().lower().rstrip("/")
                if not url_key or url_key not in info_by_url:
                    continue
                iref = info_by_url[url_key]
                for key in ("phrase", "highlight_boxes", "evidence_units", "unit_id", "match_quality",
                            "strength_score", "char_start", "char_end", "source_id"):
                    if not ref.get(key) and iref.get(key):
                        ref[key] = iref[key]
        layout_body = body
        if "class='citation'" in layout_body or 'class="citation"' in layout_body:
            layout_body = _anchors_to_bracket_markers(layout_body)
        layout_body = _format_notebook_style_layout(layout_body)
        enriched = render_fast_citation_links(answer=layout_body, refs=refs, citation_mode="inline")
        enriched = _inject_inline_citations(enriched, refs)
        enriched = _normalize_explicit_page_prose(enriched)
        from .visible import _normalize_visible_inline_citations

        enriched = _normalize_visible_inline_citations(enriched)
        enriched = _dedupe_duplicate_answer_passes(enriched)
        if "class='citation'" in enriched or 'class="citation"' in enriched:
            return f"{enriched.rstrip()}\n\n{tail.lstrip()}"
        from .anchors import _citation_anchor

        fallback_refs = " ".join(
            [_citation_anchor(ref) for ref in refs[: min(3, len(refs))] if _citation_anchor(ref)]
        )
        return f"{enriched.rstrip()}\n\nEvidence: {fallback_refs}\n\n{tail.lstrip()}"

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
        enriched = _normalize_explicit_page_prose(enriched)
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
    return _dedupe_duplicate_answer_passes(raw_text)


_FAST_QA_FILLER_OPENING_RE = re.compile(
    r"^(?:"
    r"Based\s+on\s+(?:the\s+|this\s+|my\s+|your\s+|available\s+|retrieved\s+|indexed\s+|provided\s+)?"
    r"(?:context|information|evidence|analysis|research|sources?|data|content|documents?)"
    r"[^.\n]*[.\n]\s*"
    r"|It(?:'s|\s+is)\s+(?:important|worth\s+noting|worth\s+mentioning|essential)\s+to\s+note\s+that"
    r"[^.\n]*[.\n]\s*"
    r"|As\s+an?\s+(?:AI|artificial\s+intelligence|language\s+model|AI\s+assistant|AI\s+language\s+model)"
    r"[^.\n]*[.\n]\s*"
    r"|(?:Great|Excellent|Good|Interesting)\s+question\s*[!.][^\n]*\n?"
    r"|(?:Certainly|Of\s+course|Absolutely|Sure)\s*[!.][^\n]*\n?"
    r"|I(?:'d|\s+would|\s+will|'ll)\s+be\s+happy\s+to[^.\n]*[.\n]\s*"
    r"|Thank\s+you\s+for\s+(?:asking|your\s+question)[^.\n]*[.\n]\s*"
    r")+",
    re.IGNORECASE,
)


def normalize_fast_answer(answer: str, *, question: str = "") -> str:
    text = (answer or "").strip()
    if not text:
        return ""

    # Strip filler openings (safety net — system prompt instructs model to avoid these)
    # Preserve any citation markers [N] that appear in the stripped preamble
    filler_match = _FAST_QA_FILLER_OPENING_RE.match(text)
    if filler_match and filler_match.end() < len(text):
        stripped_part = text[:filler_match.end()]
        remaining = text[filler_match.end():].strip()
        if len(remaining) >= 40:
            # Move any citation markers from the stripped preamble to the start of remaining text
            preamble_citations = re.findall(r"\[\d{1,4}\]", stripped_part)
            prefix = " ".join(preamble_citations) + " " if preamble_citations else ""
            text = prefix + (remaining[0].upper() + remaining[1:] if remaining else text)

    # Normalize heading hierarchy: H1 → H2, H4+ → H3
    text = re.sub(r"(^|\n)#\s+", r"\1## ", text)
    text = re.sub(r"(^|\n)#{4,}\s+", r"\1### ", text)

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
