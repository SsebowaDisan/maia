from __future__ import annotations

import html
import re
from typing import Any


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


def render_fast_citation_links(
    answer: str,
    refs: list[dict[str, Any]],
    citation_mode: str | None,
) -> str:
    if not answer.strip():
        return answer

    mode = (citation_mode or "").strip().lower()
    if mode == "off":
        return answer

    ref_by_id: dict[int, dict[str, Any]] = {
        int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
    }
    max_ref = len(ref_by_id)

    def replace_ref(match: re.Match[str]) -> str:
        ref_num = int(match.group(1))
        if ref_num < 1 or ref_num > max_ref:
            return match.group(0)
        ref = ref_by_id.get(ref_num, {})
        file_id = str(ref.get("source_id", "") or "").strip()
        page_label = str(ref.get("page_label", "") or "").strip()
        attrs = [f"href='#evidence-{ref_num}'", f"id='citation-{ref_num}'", "class='citation'"]
        if file_id:
            attrs.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
        if page_label:
            attrs.append(f"data-page='{html.escape(page_label, quote=True)}'")
        return f"<a {' '.join(attrs)}>" f"[{ref_num}]</a>"

    enriched = re.sub(r"\[(\d{1,3})\]", replace_ref, answer)

    if "class='citation'" in enriched or 'class="citation"' in enriched:
        return enriched

    if not refs:
        return enriched

    fallback_refs = " ".join(
        [
            (
                f"<a class='citation' href='#evidence-{ref['id']}' id='citation-{ref['id']}'"
                + (
                    f" data-file-id='{html.escape(str(ref.get('source_id', '') or ''), quote=True)}'"
                    if str(ref.get("source_id", "") or "").strip()
                    else ""
                )
                + (
                    f" data-page='{html.escape(str(ref.get('page_label', '') or ''), quote=True)}'"
                    if str(ref.get("page_label", "") or "").strip()
                    else ""
                )
                + f">[{ref['id']}]</a>"
            )
            for ref in refs[: min(3, len(refs))]
        ]
    )
    return f"{enriched}\n\nEvidence: {fallback_refs}"


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
        details_file_attr = (
            f" data-file-id='{html.escape(source_id, quote=True)}'" if source_id else ""
        )
        source_label = source_name
        if ref_id > 0:
            source_label = f"[{ref_id}] {source_name}"
        block = (
            f"<details class='evidence'{details_id}{details_file_attr} {'open' if not info_blocks else ''}>"
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
