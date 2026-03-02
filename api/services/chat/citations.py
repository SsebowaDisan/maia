from __future__ import annotations

import html
import re
from typing import Any

CITATION_MODE_INLINE = "inline"
CITATION_MODE_FOOTNOTE = "footnote"
ALLOWED_CITATION_MODES = {"highlight", CITATION_MODE_INLINE, CITATION_MODE_FOOTNOTE}
_CITATION_SECTION_RE = re.compile(
    r"(^|\n)\s*##\s+(Evidence\s+Citations|Sources)\b",
    flags=re.IGNORECASE,
)
_EVIDENCE_SUFFIX_RE = re.compile(r"\n\nEvidence:\s", flags=re.IGNORECASE)
_DETAILS_BLOCK_RE = re.compile(
    r"(<details\b[^>]*>)([\s\S]*?)</details>",
    flags=re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _citation_anchor(ref: dict[str, Any]) -> str:
    ref_id = int(ref.get("id", 0) or 0)
    if ref_id <= 0:
        return ""
    file_id = str(ref.get("source_id", "") or "").strip()
    page_label = str(ref.get("page_label", "") or "").strip()
    phrase = str(ref.get("phrase", "") or "").strip()
    attrs = [f"href='#evidence-{ref_id}'", f"id='citation-{ref_id}'", "class='citation'"]
    if file_id:
        attrs.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
    if page_label:
        attrs.append(f"data-page='{html.escape(page_label, quote=True)}'")
    if phrase:
        attrs.append(f"data-phrase='{html.escape(phrase[:360], quote=True)}'")
    return f"<a {' '.join(attrs)}>[{ref_id}]</a>"


def _clean_text(fragment: str) -> str:
    if not fragment:
        return ""
    without_tags = _HTML_TAG_RE.sub(" ", fragment)
    plain = html.unescape(without_tags)
    return _SPACE_RE.sub(" ", plain).strip()


def _extract_phrase_from_details_body(body_html: str) -> str:
    if not body_html:
        return ""
    extract_match = re.search(
        r"<div[^>]*class=['\"][^'\"]*evidence-content[^'\"]*['\"][^>]*>\s*"
        r"<b>\s*Extract:\s*</b>\s*([\s\S]*?)</div>",
        body_html,
        flags=re.IGNORECASE,
    )
    if not extract_match:
        extract_match = re.search(
            r"<div[^>]*>\s*<b>\s*Extract:\s*</b>\s*([\s\S]*?)</div>",
            body_html,
            flags=re.IGNORECASE,
        )
    phrase = _clean_text(extract_match.group(1) if extract_match else "")
    if not phrase:
        return ""
    if len(phrase) <= 360:
        return phrase
    clipped = phrase[:360]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.strip()


def _split_answer_for_inline_injection(answer: str) -> tuple[str, str]:
    text = str(answer or "")
    section_match = _CITATION_SECTION_RE.search(text)
    if section_match:
        return text[: section_match.start()].rstrip(), text[section_match.start() :].lstrip()
    suffix_match = _EVIDENCE_SUFFIX_RE.search(text)
    if suffix_match:
        return text[: suffix_match.start()].rstrip(), text[suffix_match.start() :].lstrip()
    return text, ""


def _has_inline_citation_markers(answer: str) -> bool:
    body, _ = _split_answer_for_inline_injection(answer)
    text = str(body or "")
    if not text.strip():
        return False
    return bool(
        "class='citation'" in text
        or 'class="citation"' in text
        or re.search(r"\[\d{1,3}\]", text)
    )


def _inject_inline_citations(answer: str, refs: list[dict[str, Any]]) -> str:
    text = str(answer or "")
    if not text.strip() or not refs:
        return text
    if _has_inline_citation_markers(text):
        return text

    body, tail = _split_answer_for_inline_injection(text)
    lines = body.splitlines()
    ref_limit = max(1, min(len(refs), 2))
    injected = 0

    for index, row in enumerate(lines):
        stripped = row.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "-", "*", ">", "|")):
            continue
        if re.match(r"^\d+\.\s+", stripped):
            continue
        if stripped.startswith("<"):
            continue
        if len(stripped) < 18:
            continue
        anchor = _citation_anchor(refs[injected % len(refs)])
        if not anchor:
            continue
        lines[index] = f"{row.rstrip()} {anchor}"
        injected += 1
        if injected >= ref_limit:
            break

    if injected == 0 and body.strip():
        first_anchor = _citation_anchor(refs[0])
        if first_anchor:
            body = f"{body.rstrip()} {first_anchor}"
    else:
        body = "\n".join(lines)

    if tail:
        return f"{body.rstrip()}\n\n{tail.lstrip()}"
    return body


def assign_fast_source_refs(
    snippets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ref_by_key: dict[tuple[str, str], int] = {}
    refs: list[dict[str, Any]] = []
    enriched: list[dict[str, Any]] = []

    for snippet in snippets:
        source_id = str(snippet.get("source_id", "") or "").strip()
        source_name = str(snippet.get("source_name", "Indexed file"))
        page_label = str(snippet.get("page_label", "") or "").strip()
        key = (source_id or source_name, page_label)
        ref_id = ref_by_key.get(key)
        if ref_id is None:
            ref_id = len(refs) + 1
            ref_by_key[key] = ref_id
            label = source_name
            if page_label:
                label += f" (page {page_label})"
            refs.append(
                {
                    "id": ref_id,
                    "source_id": source_id,
                    "source_name": source_name,
                    "page_label": page_label,
                    "label": label,
                }
            )

        enriched_item = dict(snippet)
        enriched_item["ref_id"] = ref_id
        enriched.append(enriched_item)

    return enriched, refs


def resolve_required_citation_mode(citation_mode: str | None) -> str:
    mode = (citation_mode or "").strip().lower()
    if mode == CITATION_MODE_INLINE:
        return CITATION_MODE_INLINE
    return CITATION_MODE_INLINE


def render_fast_citation_links(
    answer: str,
    refs: list[dict[str, Any]],
    citation_mode: str | None,
) -> str:
    if not answer.strip():
        return answer

    if "class='citation'" in answer or 'class="citation"' in answer:
        # Already linked: avoid a second replacement pass that can nest anchors.
        return _inject_inline_citations(answer, refs)

    ref_by_id: dict[int, dict[str, Any]] = {
        int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
    }
    max_ref = len(ref_by_id)

    def replace_ref(match: re.Match[str]) -> str:
        ref_num = int(match.group(1))
        if ref_num < 1 or ref_num > max_ref:
            return match.group(0)
        ref = ref_by_id.get(ref_num, {})
        return _citation_anchor(ref) or match.group(0)

    enriched = re.sub(r"\[(\d{1,3})\]", replace_ref, answer)
    enriched = _inject_inline_citations(enriched, refs)

    if "class='citation'" in enriched or 'class="citation"' in enriched:
        return enriched

    if not refs:
        return enriched

    fallback_refs = " ".join([_citation_anchor(ref) for ref in refs[: min(3, len(refs))] if _citation_anchor(ref)])
    return f"{enriched}\n\nEvidence: {fallback_refs}"


def _extract_info_refs(info_html: str) -> list[dict[str, Any]]:
    text = str(info_html or "")
    if not text:
        return []

    refs: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for match in _DETAILS_BLOCK_RE.finditer(text):
        tag = match.group(1)
        body_html = match.group(2)
        id_match = re.search(r"id=['\"]evidence-(\d{1,4})['\"]", tag, flags=re.IGNORECASE)
        if not id_match:
            continue
        ref_id = int(id_match.group(1))
        if ref_id <= 0 or ref_id in seen_ids:
            continue
        seen_ids.add(ref_id)
        source_id_match = re.search(r"data-file-id=['\"]([^'\"]+)['\"]", tag, flags=re.IGNORECASE)
        page_match = re.search(r"data-page=['\"]([^'\"]+)['\"]", tag, flags=re.IGNORECASE)
        if not page_match:
            summary_match = re.search(
                r"<summary[^>]*>[\s\S]*?page\s+(\d{1,4})[\s\S]*?</summary>",
                body_html[:420],
                flags=re.IGNORECASE,
            )
            if summary_match:
                page_label = summary_match.group(1).strip()
            else:
                page_label = ""
        else:
            page_label = page_match.group(1).strip()
        phrase = _extract_phrase_from_details_body(body_html)
        refs.append(
            {
                "id": ref_id,
                "source_id": source_id_match.group(1).strip() if source_id_match else "",
                "page_label": page_label,
                "label": f"Evidence {ref_id}",
                "phrase": phrase,
            }
        )
    refs.sort(key=lambda item: int(item.get("id", 0) or 0))
    return refs


def enforce_required_citations(
    *,
    answer: str,
    info_html: str,
    citation_mode: str | None,
) -> str:
    text = (answer or "").strip()
    if not text:
        return text

    mode = resolve_required_citation_mode(citation_mode)
    refs = _extract_info_refs(info_html)
    enriched = render_fast_citation_links(answer=text, refs=refs, citation_mode=mode)
    enriched = _inject_inline_citations(enriched, refs)
    if "class='citation'" in enriched or 'class="citation"' in enriched:
        return enriched
    if refs:
        return enriched
    return (
        f"{enriched}\n\n"
        "Evidence: internal execution trace (no external source references were returned by the retrieval pipeline)."
    )


def append_required_citation_suffix(*, answer: str, info_html: str) -> str:
    raw_text = str(answer or "")
    if not raw_text.strip():
        return ""
    if "class='citation'" in raw_text or 'class="citation"' in raw_text:
        return raw_text

    refs = _extract_info_refs(info_html)
    if refs:
        enriched = render_fast_citation_links(
            answer=raw_text,
            refs=refs,
            citation_mode=CITATION_MODE_INLINE,
        )
        enriched = _inject_inline_citations(enriched, refs)
        if "class='citation'" in enriched or 'class="citation"' in enriched:
            return enriched
        fallback_refs = " ".join([_citation_anchor(ref) for ref in refs[: min(3, len(refs))] if _citation_anchor(ref)])
        return f"{enriched}\n\nEvidence: {fallback_refs}"
    return (
        f"{raw_text}\n\n"
        "Evidence: internal execution trace (no external source references were returned by the retrieval pipeline)."
    )


def normalize_fast_answer(answer: str) -> str:
    text = (answer or "").strip()
    if not text:
        return ""

    # Keep headings readable when models place them mid-line.
    text = re.sub(r"(?<!\n)(#{2,6}\s+)", r"\n\n\1", text)
    # Collapse duplicated heading markers like "### ## Title" into a single heading.
    text = re.sub(r"(^|\n)\s*#{1,6}\s*#{1,6}\s*", r"\1## ", text)

    # Remove malformed bold markers that often break markdown rendering.
    malformed_bold = bool(re.search(r"#{2,6}\s*\*\*|\*\*[^*]+-\s*\*\*", text))
    if malformed_bold or text.count("**") % 2 == 1:
        text = text.replace("**", "")

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_fast_info_html(
    snippets_with_refs: list[dict[str, Any]],
    *,
    max_blocks: int = 6,
) -> str:
    info_blocks: list[str] = []
    rendered_refs: set[int] = set()
    for snippet in snippets_with_refs:
        ref_id = int(snippet.get("ref_id", 0) or 0)
        if ref_id > 0 and ref_id in rendered_refs:
            continue
        if ref_id > 0:
            rendered_refs.add(ref_id)

        source_name = html.escape(str(snippet.get("source_name", "Indexed file")))
        page_label = html.escape(str(snippet.get("page_label", "") or ""))
        excerpt = html.escape(str(snippet.get("text", "") or "")[:1400])
        image_origin = snippet.get("image_origin")
        summary_label = f"Evidence [{ref_id}]" if ref_id > 0 else "Evidence"
        if page_label:
            summary_label += f" - page {page_label}"

        details_id = f" id='evidence-{ref_id}'" if ref_id > 0 else ""
        source_id = str(snippet.get("source_id", "") or "").strip()
        details_page_attr = f" data-page='{page_label}'" if page_label else ""
        details_file_attr = (
            f" data-file-id='{html.escape(source_id, quote=True)}'" if source_id else ""
        )
        source_label = source_name
        if ref_id > 0:
            source_label = f"[{ref_id}] {source_name}"
        block = (
            f"<details class='evidence'{details_id}{details_file_attr}{details_page_attr} {'open' if not info_blocks else ''}>"
            f"<summary><i>{summary_label}</i></summary>"
            f"<div><b>Source:</b> {source_label}</div>"
            f"<div class='evidence-content'><b>Extract:</b> {excerpt}</div>"
        )
        if isinstance(image_origin, str) and image_origin.startswith("data:image/"):
            safe_src = html.escape(image_origin, quote=True)
            block += "<figure>" f"<img src=\"{safe_src}\" alt=\"evidence image\"/>" "</figure>"
        block += "</details>"
        info_blocks.append(block)
        if len(info_blocks) >= max_blocks:
            break
    return "".join(info_blocks)
