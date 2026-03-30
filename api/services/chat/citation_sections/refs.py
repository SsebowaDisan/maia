from __future__ import annotations

import re
from itertools import combinations
from typing import Any

from ..constants import MAIA_CITATION_CONTRADICTION_SIGNALS_ENABLED, MAIA_CITATION_STRENGTH_ORDERING_ENABLED, MAIA_SOURCE_USAGE_HEATMAP_ENABLED
from .context import _tokens
from .shared import (
    CITATION_MODE_INLINE,
    _CITATION_ANCHOR_RE,
    _HTML_TAG_RE,
    _INLINE_REF_TOKEN_RE,
    _SENTENCE_SEGMENT_RE,
    _merge_highlight_boxes,
    _normalize_highlight_boxes,
    _score_value,
    _snippet_signature_text,
    _snippet_strength_score,
    _source_type_from_name,
    _to_int,
)


def _credibility_rank(value: Any) -> int:
    normalized = str(value or "").strip().lower()
    if normalized == "platform":
        return 4
    if normalized == "high":
        return 3
    if normalized == "medium":
        return 2
    if normalized == "low":
        return 1
    return 0


def _plain_text_for_claim_analysis(answer_text: str) -> str:
    text = str(answer_text or "")
    if not text:
        return ""
    text = _CITATION_ANCHOR_RE.sub(lambda match: str(match.group(2) or ""), text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def assign_fast_source_refs(
    snippets: list[dict[str, Any]],
    *,
    strength_ordering: bool | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    def _normalize_evidence_units(raw: Any, *, limit: int = 12) -> list[dict[str, Any]]:
        rows = raw if isinstance(raw, list) else []
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = " ".join(str(row.get("text", "") or "").split()).strip()
            if len(text) < 8:
                continue
            try:
                char_start = int(row.get("char_start", 0) or 0) if str(row.get("char_start", "")).strip() else 0
            except Exception:
                char_start = 0
            try:
                char_end = int(row.get("char_end", 0) or 0) if str(row.get("char_end", "")).strip() else 0
            except Exception:
                char_end = 0
            boxes = _normalize_highlight_boxes(row.get("highlight_boxes"))
            if not boxes:
                continue
            key = f"{char_start}|{char_end}|{text[:120].lower()}"
            if key in seen:
                continue
            seen.add(key)
            item: dict[str, Any] = {
                "text": text[:240],
                "highlight_boxes": boxes,
            }
            if char_start > 0:
                item["char_start"] = char_start
            if char_end > char_start:
                item["char_end"] = char_end
            output.append(item)
            if len(output) >= max(1, int(limit)):
                break
        return output

    def _merge_evidence_units(existing: Any, incoming: Any, *, limit: int = 12) -> list[dict[str, Any]]:
        return _normalize_evidence_units([*_normalize_evidence_units(existing, limit=limit), *_normalize_evidence_units(incoming, limit=limit)], limit=limit)

    ref_by_key: dict[tuple[str, str, str], int] = {}
    ref_index_by_id: dict[int, int] = {}
    refs: list[dict[str, Any]] = []
    enriched: list[dict[str, Any]] = []
    ordering_enabled = (
        MAIA_CITATION_STRENGTH_ORDERING_ENABLED if strength_ordering is None else bool(strength_ordering)
    )
    # Sequential counter to ensure distinct chunks never collapse when all
    # metadata differentiators (unit_id, selector, char offsets) are missing.
    _seq_by_source: dict[str, int] = {}

    for snippet in snippets:
        file_id = str(snippet.get("file_id", "") or "").strip()
        source_id = file_id or str(snippet.get("source_id", "") or "").strip()
        source_name = str(snippet.get("source_name", "Indexed file"))
        is_primary_source = bool(snippet.get("is_primary_source"))
        source_name_url = source_name if source_name.strip().lower().startswith(("http://", "https://")) else ""
        from .shared import _normalize_source_url

        source_url = _normalize_source_url(
            snippet.get("source_url")
            or snippet.get("page_url")
            or snippet.get("url")
            or source_name_url
        )
        page_label = str(snippet.get("page_label", "") or "").strip()
        unit_id = str(snippet.get("unit_id", "") or "").strip()
        snippet_selector = str(snippet.get("selector", "") or "").strip()
        match_quality = str(snippet.get("match_quality", "") or "").strip() or "estimated"
        try:
            char_start = int(snippet.get("char_start", 0) or 0) if str(snippet.get("char_start", "")).strip() else 0
        except Exception:
            char_start = 0
        try:
            char_end = int(snippet.get("char_end", 0) or 0) if str(snippet.get("char_end", "")).strip() else 0
        except Exception:
            char_end = 0
        snippet_boxes = _normalize_highlight_boxes(snippet.get("highlight_boxes"))
        snippet_units = _normalize_evidence_units(snippet.get("evidence_units"))
        phrase = _snippet_signature_text(snippet.get("text", ""))
        snippet_strength = _snippet_strength_score(snippet)
        dedup_span = (
            unit_id
            if unit_id
            else (
                snippet_selector
                or (
                    f"{char_start}:{char_end}"
                    if char_start > 0 and char_end > char_start
                    else phrase
                )
            )
        )
        key = (source_id or source_name, page_label, dedup_span)
        # When no strong identifier exists, use a sequential index to prevent
        # chunks with genuinely different text from collapsing into one ref.
        if not unit_id and not snippet_selector and not (char_start > 0 and char_end > char_start):
            source_slot = source_id or source_name
            if dedup_span:
                key = (source_slot, page_label, dedup_span)
            else:
                seq_idx = _seq_by_source.get(source_slot, 0)
                _seq_by_source[source_slot] = seq_idx + 1
                key = (source_slot, page_label, f"seq::{seq_idx}")
        ref_id = ref_by_key.get(key)
        if ref_id is None:
            ref_id = len(refs) + 1
            ref_by_key[key] = ref_id
            ref_index_by_id[ref_id] = len(refs)
            label = source_name
            if page_label:
                label += f" (page {page_label})"
            refs.append(
                {
                    "id": ref_id,
                    "file_id": file_id,
                    "source_id": source_id,
                    "source_name": source_name,
                    "page_label": page_label,
                    "label": label,
                    "phrase": phrase,
                    "source_url": source_url,
                    "unit_id": unit_id,
                    "selector": snippet_selector,
                    "char_start": char_start,
                    "char_end": char_end,
                    "match_quality": match_quality,
                    "highlight_boxes": snippet_boxes,
                    "evidence_units": snippet_units,
                    "strength_score": snippet_strength,
                    "is_primary_source": is_primary_source,
                    "source_type": _source_type_from_name(source_name),
                    "credibility_tier": str(snippet.get("credibility_tier", "") or "").strip().lower() or None,
                }
            )
        else:
            existing_idx = ref_index_by_id.get(ref_id)
            if existing_idx is not None:
                existing_ref = refs[existing_idx]
                if snippet_boxes:
                    existing_ref["highlight_boxes"] = _merge_highlight_boxes(
                        _normalize_highlight_boxes(existing_ref.get("highlight_boxes")),
                        snippet_boxes,
                    )
                if snippet_units:
                    existing_ref["evidence_units"] = _merge_evidence_units(
                        existing_ref.get("evidence_units"),
                        snippet_units,
                    )
                from .shared import _normalize_source_url

                if source_url and not _normalize_source_url(existing_ref.get("source_url")):
                    existing_ref["source_url"] = source_url
                if file_id and not str(existing_ref.get("file_id", "") or "").strip():
                    existing_ref["file_id"] = file_id
                if is_primary_source:
                    existing_ref["is_primary_source"] = True
                existing_ref["strength_score"] = max(
                    _score_value(existing_ref.get("strength_score")),
                    snippet_strength,
                )
                incoming_credibility = str(snippet.get("credibility_tier", "") or "").strip().lower() or None
                if _credibility_rank(incoming_credibility) > _credibility_rank(existing_ref.get("credibility_tier")):
                    existing_ref["credibility_tier"] = incoming_credibility
                if unit_id and not str(existing_ref.get("unit_id", "")).strip():
                    existing_ref["unit_id"] = unit_id
                if snippet_selector and not str(existing_ref.get("selector", "")).strip():
                    existing_ref["selector"] = snippet_selector
                if match_quality and str(existing_ref.get("match_quality", "")).strip() in {"", "estimated"}:
                    existing_ref["match_quality"] = match_quality
                if char_start > 0 and int(existing_ref.get("char_start", 0) or 0) <= 0:
                    existing_ref["char_start"] = char_start
                if char_end > char_start and int(existing_ref.get("char_end", 0) or 0) <= 0:
                    existing_ref["char_end"] = char_end

        enriched_item = dict(snippet)
        enriched_item["ref_id"] = ref_id
        enriched_item["strength_score"] = snippet_strength
        enriched_item["unit_id"] = unit_id
        if snippet_selector:
            enriched_item["selector"] = snippet_selector
        if char_start > 0:
            enriched_item["char_start"] = char_start
        if char_end > char_start:
            enriched_item["char_end"] = char_end
        enriched_item["match_quality"] = match_quality
        enriched_item["is_primary_source"] = is_primary_source
        if snippet_boxes:
            enriched_item["highlight_boxes"] = snippet_boxes
        if snippet_units:
            enriched_item["evidence_units"] = snippet_units
        if source_url:
            enriched_item["source_url"] = source_url
        enriched.append(enriched_item)

    if ordering_enabled and refs:
        ranked_refs = sorted(
            refs,
            key=lambda ref: (
                0 if bool(ref.get("is_primary_source")) else 1,
                -_score_value(ref.get("strength_score")),
                -_score_value(ref.get("llm_trulens_score")),
                str(ref.get("source_id", "") or ""),
                str(ref.get("page_label", "") or ""),
                str(ref.get("unit_id", "") or ""),
                str(ref.get("phrase", "") or ""),
            ),
        )
        old_to_new: dict[int, int] = {}
        normalized_refs: list[dict[str, Any]] = []
        for index, ref in enumerate(ranked_refs, start=1):
            previous_id = int(ref.get("id", 0) or 0)
            if previous_id > 0:
                old_to_new[previous_id] = index
            next_ref = dict(ref)
            next_ref["id"] = index
            normalized_refs.append(next_ref)
        refs = normalized_refs
        normalized_enriched: list[dict[str, Any]] = []
        for row in enriched:
            previous_id = int(row.get("ref_id", 0) or 0)
            next_row = dict(row)
            if previous_id > 0:
                next_row["ref_id"] = old_to_new.get(previous_id, previous_id)
            normalized_enriched.append(next_row)
        enriched = sorted(
            normalized_enriched,
            key=lambda row: (
                int(row.get("ref_id", 0) or 0),
                -_score_value(row.get("strength_score")),
            ),
        )

    return enriched, refs


def collect_cited_ref_ids(answer: str) -> list[int]:
    text = str(answer or "")
    if not text:
        return []
    seen: set[int] = set()
    ordered: list[int] = []
    for match in re.finditer(r"#evidence-(\d{1,4})", text, flags=re.IGNORECASE):
        ref_id = int(match.group(1))
        if ref_id <= 0 or ref_id in seen:
            continue
        seen.add(ref_id)
        ordered.append(ref_id)
    if ordered:
        return ordered
    for match in _INLINE_REF_TOKEN_RE.finditer(text):
        ref_id = int(match.group(1))
        if ref_id <= 0 or ref_id in seen:
            continue
        seen.add(ref_id)
        ordered.append(ref_id)
    return ordered


def build_source_usage(
    *,
    snippets_with_refs: list[dict[str, Any]],
    refs: list[dict[str, Any]],
    answer_text: str,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    if enabled is None:
        enabled = MAIA_SOURCE_USAGE_HEATMAP_ENABLED
    if not enabled:
        return []
    if not snippets_with_refs and not refs:
        return []

    ref_by_id = {int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0}
    cited_ref_ids = set(collect_cited_ref_ids(answer_text))

    bucket_by_source: dict[str, dict[str, Any]] = {}
    for snippet in snippets_with_refs:
        source_id = str(snippet.get("source_id", "") or "").strip()
        source_name = str(snippet.get("source_name", "Indexed file") or "Indexed file")
        source_key = source_id or f"name:{source_name}"
        bucket = bucket_by_source.get(source_key)
        if bucket is None:
            bucket = {
                "source_id": source_id,
                "source_name": source_name,
                "source_type": _source_type_from_name(source_name),
                "credibility_tier": str(snippet.get("credibility_tier", "") or "").strip().lower() or None,
                "retrieved_count": 0,
                "cited_count": 0,
                "max_strength_score": 0.0,
                "avg_strength_score": 0.0,
                "_strength_total": 0.0,
                "_strength_count": 0,
            }
            bucket_by_source[source_key] = bucket

        bucket["retrieved_count"] = int(bucket.get("retrieved_count", 0)) + 1
        strength = _score_value(snippet.get("strength_score"))
        bucket["max_strength_score"] = max(_score_value(bucket.get("max_strength_score")), strength)
        bucket["_strength_total"] = _score_value(bucket.get("_strength_total")) + strength
        bucket["_strength_count"] = int(bucket.get("_strength_count", 0)) + 1
        incoming_credibility = str(snippet.get("credibility_tier", "") or "").strip().lower() or None
        if _credibility_rank(incoming_credibility) > _credibility_rank(bucket.get("credibility_tier")):
            bucket["credibility_tier"] = incoming_credibility

        ref_id = int(snippet.get("ref_id", 0) or 0)
        if ref_id > 0 and ref_id in cited_ref_ids:
            bucket["cited_count"] = int(bucket.get("cited_count", 0)) + 1

    for ref_id in cited_ref_ids:
        ref = ref_by_id.get(ref_id)
        if not ref:
            continue
        source_id = str(ref.get("source_id", "") or "").strip()
        source_name = str(ref.get("source_name", "Indexed file") or "Indexed file")
        source_key = source_id or f"name:{source_name}"
        bucket = bucket_by_source.get(source_key)
        if bucket is None:
            strength = _score_value(ref.get("strength_score"))
            bucket = {
                "source_id": source_id,
                "source_name": source_name,
                "source_type": _source_type_from_name(source_name),
                "credibility_tier": str(ref.get("credibility_tier", "") or "").strip().lower() or None,
                "retrieved_count": 0,
                "cited_count": 1,
                "max_strength_score": strength,
                "avg_strength_score": strength,
                "_strength_total": strength,
                "_strength_count": 1,
            }
            bucket_by_source[source_key] = bucket
            continue
        bucket["cited_count"] = max(int(bucket.get("cited_count", 0)), 1)

    total_cited = sum(max(0, int(bucket.get("cited_count", 0))) for bucket in bucket_by_source.values())
    usage_rows: list[dict[str, Any]] = []
    for bucket in bucket_by_source.values():
        strength_count = max(1, int(bucket.get("_strength_count", 0)))
        avg_strength = _score_value(bucket.get("_strength_total")) / float(strength_count)
        cited_count = max(0, int(bucket.get("cited_count", 0)))
        usage_rows.append(
            {
                "source_id": str(bucket.get("source_id", "") or ""),
                "source_name": str(bucket.get("source_name", "Indexed file") or "Indexed file"),
                "source_type": str(bucket.get("source_type", "file") or "file"),
                "credibility_tier": str(bucket.get("credibility_tier", "") or "").strip().lower() or None,
                "retrieved_count": max(0, int(bucket.get("retrieved_count", 0))),
                "cited_count": cited_count,
                "max_strength_score": round(_score_value(bucket.get("max_strength_score")), 6),
                "avg_strength_score": round(avg_strength, 6),
                "citation_share": round((float(cited_count) / float(total_cited)) if total_cited > 0 else 0.0, 6),
            }
        )

    usage_rows.sort(
        key=lambda item: (
            -int(item.get("cited_count", 0)),
            -int(item.get("retrieved_count", 0)),
            -_score_value(item.get("max_strength_score")),
            str(item.get("source_name", "") or ""),
        )
    )
    return usage_rows


def build_claim_signal_summary(
    *,
    answer_text: str,
    refs: list[dict[str, Any]],
    enabled: bool | None = None,
) -> dict[str, Any]:
    if enabled is None:
        enabled = MAIA_CITATION_CONTRADICTION_SIGNALS_ENABLED
    if not enabled:
        return {}

    text = _plain_text_for_claim_analysis(answer_text)
    if not text.strip() or not refs:
        return {}

    ref_by_id: dict[int, dict[str, Any]] = {
        int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
    }
    if not ref_by_id:
        return {}

    rows: list[dict[str, Any]] = []
    supported = 0
    contradicted = 0
    mixed = 0

    for segment_match in _SENTENCE_SEGMENT_RE.finditer(text):
        segment = segment_match.group(0)
        if not segment.strip():
            continue
        ref_ids = {
            int(match)
            for match in re.findall(r"#evidence-(\d{1,4})", segment, flags=re.IGNORECASE)
            if int(match) in ref_by_id
        }
        if not ref_ids:
            ref_ids = {
                int(match)
                for match in re.findall(r"(?:\[|【|ã€|\{)\s*(\d{1,4})\s*(?:\]|】|ã€‘|\})", segment)
                if int(match) in ref_by_id
            }
        if not ref_ids:
            continue

        from .shared import _clean_text

        cleaned_claim = _clean_text(
            re.sub(
                r"(?:\[|【|ã€|\{)\s*(\d{1,4})\s*(?:\]|】|ã€‘|\})",
                "",
                segment,
            )
        )
        if len(cleaned_claim) < 16:
            continue

        support_votes = 0
        contradiction_votes = 0
        if len(ref_ids) >= 2:
            for left_id, right_id in combinations(sorted(ref_ids), 2):
                left = ref_by_id.get(left_id, {})
                right = ref_by_id.get(right_id, {})
                left_tokens = _tokens(" ".join([str(left.get("phrase", "") or ""), str(left.get("label", "") or ""), str(left.get("source_name", "") or "")]))
                right_tokens = _tokens(" ".join([str(right.get("phrase", "") or ""), str(right.get("label", "") or ""), str(right.get("source_name", "") or "")]))
                if not left_tokens or not right_tokens:
                    continue
                inter = len(left_tokens & right_tokens)
                union = len(left_tokens | right_tokens)
                jaccard = (inter / float(union)) if union > 0 else 0.0
                if jaccard >= 0.22:
                    support_votes += 1
                elif jaccard <= 0.08:
                    contradiction_votes += 1

        if support_votes > 0 and contradiction_votes > 0:
            status = "mixed"
            mixed += 1
        elif support_votes > 0:
            status = "supported"
            supported += 1
        elif contradiction_votes > 0:
            status = "contradicted"
            contradicted += 1
        else:
            status = "insufficient"

        rows.append(
            {
                "claim": cleaned_claim,
                "ref_ids": sorted(ref_ids),
                "status": status,
                "support_votes": support_votes,
                "contradiction_votes": contradiction_votes,
            }
        )
        if len(rows) >= 16:
            break

    if not rows:
        return {}
    return {
        "claims_evaluated": len(rows),
        "supported_claims": supported,
        "contradicted_claims": contradicted,
        "mixed_claims": mixed,
        "rows": rows,
    }


def build_citation_quality_metrics(
    *,
    snippets_with_refs: list[dict[str, Any]],
    refs: list[dict[str, Any]],
    answer_text: str,
) -> dict[str, Any]:
    cited_ref_ids = set(collect_cited_ref_ids(answer_text))
    refs_with_boxes = sum(1 for ref in refs if _normalize_highlight_boxes(ref.get("highlight_boxes")))
    refs_with_unit_id = sum(1 for ref in refs if str(ref.get("unit_id", "") or "").strip())
    refs_with_offsets = sum(
        1
        for ref in refs
        if (_to_int(ref.get("char_start", 0)) or 0) > 0
        and (_to_int(ref.get("char_end", 0)) or 0) > (_to_int(ref.get("char_start", 0)) or 0)
    )
    match_quality_counter: dict[str, int] = {}
    for ref in refs:
        quality = str(ref.get("match_quality", "") or "").strip().lower() or "estimated"
        match_quality_counter[quality] = int(match_quality_counter.get(quality, 0)) + 1
    return {
        "retrieved_snippets": len(snippets_with_refs),
        "total_refs": len(refs),
        "cited_refs": len(cited_ref_ids),
        "refs_with_boxes": refs_with_boxes,
        "refs_with_unit_id": refs_with_unit_id,
        "refs_with_offsets": refs_with_offsets,
        "anchor_attribute_completeness": (
            round(((refs_with_boxes + refs_with_unit_id + refs_with_offsets) / float(max(1, len(refs) * 3))), 6)
            if refs
            else 0.0
        ),
        "match_quality_counts": match_quality_counter,
    }


def evaluate_citation_quality_gate(
    *,
    answer_text: str,
    refs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate whether citation quality meets minimum standards.

    Returns a dict with:
      - passed: bool — whether the answer's citations are acceptable
      - issues: list[str] — human-readable issues found
      - dominance_ratio: float — how much the top ref dominates (0-1)
      - uncited_paragraph_count: int — paragraphs without any citation
      - unique_refs_cited: int — number of distinct refs used
    """
    text = str(answer_text or "")
    if not text.strip() or not refs:
        return {"passed": True, "issues": [], "dominance_ratio": 0.0,
                "uncited_paragraph_count": 0, "unique_refs_cited": 0}

    cited_ids = collect_cited_ref_ids(text)
    unique_cited = set(cited_ids)
    total_citations = len(cited_ids)

    issues: list[str] = []

    # Check dominance — one ref shouldn't account for >65% of all citations
    dominance_ratio = 0.0
    if total_citations >= 3:
        freq: dict[int, int] = {}
        for cid in cited_ids:
            freq[cid] = freq.get(cid, 0) + 1
        dominant_count = max(freq.values()) if freq else 0
        dominance_ratio = dominant_count / max(1, total_citations)
        if dominance_ratio > 0.65 and len(refs) >= 3:
            issues.append(
                f"Citation dominance: ref [{max(freq, key=lambda k: freq[k])}] "
                f"accounts for {dominance_ratio:.0%} of all citations"
            )

    # Check paragraph coverage — count uncited substantive paragraphs
    paragraphs = re.split(r"\n\s*\n", text)
    substantive_paras = 0
    uncited_paras = 0
    for para in paragraphs:
        stripped = para.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("```"):
            continue
        if stripped.startswith("<") and stripped.endswith(">"):
            continue
        if len(stripped) < 40:
            continue
        substantive_paras += 1
        # Check if this paragraph has any citation marker
        has_ref = bool(
            re.search(r"\[\d{1,4}\]", stripped)
            or "class='citation'" in stripped
            or 'class="citation"' in stripped
        )
        if not has_ref:
            uncited_paras += 1

    if substantive_paras >= 3 and uncited_paras > substantive_paras * 0.5:
        issues.append(
            f"Low citation coverage: {uncited_paras}/{substantive_paras} "
            f"substantive paragraphs have no citation"
        )

    # Check ref diversity — for multi-page questions, expect 2+ unique refs
    if len(refs) >= 3 and len(unique_cited) <= 1 and total_citations >= 2:
        issues.append(
            f"No citation diversity: only {len(unique_cited)} unique ref(s) "
            f"cited despite {len(refs)} available"
        )

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "dominance_ratio": round(dominance_ratio, 4),
        "uncited_paragraph_count": uncited_paras,
        "unique_refs_cited": len(unique_cited),
    }


def resolve_required_citation_mode(citation_mode: str | None) -> str:
    mode = (citation_mode or "").strip().lower()
    if mode == CITATION_MODE_INLINE:
        return CITATION_MODE_INLINE
    return CITATION_MODE_INLINE
