from __future__ import annotations

import re

from .anchors import _ref_id_from_anchor_open
from .shared import _CITATION_ANCHOR_RE


def _normalize_visible_inline_citations(answer: str) -> str:
    text = str(answer or "")
    if not text:
        return text

    ref_to_display: dict[int, int] = {}
    next_display_id = 1
    last_emitted_ref_id: int | None = None
    last_anchor_end = -1
    duplicate_gap_re = re.compile(r"^[\s,;:.!?()\[\]\-_/]*$")

    def replace_anchor(match: re.Match[str]) -> str:
        nonlocal next_display_id, last_emitted_ref_id, last_anchor_end
        anchor_open, _anchor_label, anchor_close = match.groups()
        ref_id = _ref_id_from_anchor_open(anchor_open)
        if ref_id <= 0:
            return match.group(0)

        display_id = ref_to_display.get(ref_id)
        if display_id is None:
            display_id = next_display_id
            ref_to_display[ref_id] = display_id
            next_display_id = display_id + 1

        between = text[last_anchor_end : match.start()] if last_anchor_end >= 0 else ""
        if last_emitted_ref_id == ref_id and duplicate_gap_re.fullmatch(between or ""):
            last_anchor_end = match.end()
            return ""

        if re.search(r"\bdata-citation-number=['\"]\d{1,4}['\"]", anchor_open, flags=re.IGNORECASE):
            anchor_open = re.sub(
                r"data-citation-number=['\"]\d{1,4}['\"]",
                f"data-citation-number='{display_id}'",
                anchor_open,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            anchor_open = f"{anchor_open[:-1]} data-citation-number='{display_id}'>"
        if re.search(r"\bdata-evidence-id=['\"]evidence-\d{1,4}['\"]", anchor_open, flags=re.IGNORECASE):
            anchor_open = re.sub(
                r"data-evidence-id=['\"]evidence-\d{1,4}['\"]",
                f"data-evidence-id='evidence-{ref_id}'",
                anchor_open,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            anchor_open = f"{anchor_open[:-1]} data-evidence-id='evidence-{ref_id}'>"
        last_emitted_ref_id = ref_id
        last_anchor_end = match.end()
        return f"{anchor_open}[{display_id}]{anchor_close}"

    normalized = _CITATION_ANCHOR_RE.sub(replace_anchor, text)
    if normalized == text:
        return text

    rebuilt: list[str] = []
    cursor = 0
    for match in _CITATION_ANCHOR_RE.finditer(normalized):
        outside = normalized[cursor : match.start()]
        outside = re.sub(r"(?:\[|【|ã€|\{)\s*\d{1,4}\s*(?:\]|】|ã€‘|\})", "", outside)
        rebuilt.append(outside)
        rebuilt.append(match.group(0))
        cursor = match.end()
    tail = normalized[cursor:]
    tail = re.sub(r"(?:\[|【|ã€|\{)\s*\d{1,4}\s*(?:\]|】|ã€‘|\})", "", tail)
    rebuilt.append(tail)
    normalized = "".join(rebuilt)

    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = re.sub(r"\(\s*\)", "", normalized)
    return normalized
