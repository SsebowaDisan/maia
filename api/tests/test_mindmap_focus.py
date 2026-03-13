"""Tests for the mindmap_focus schema, filtering contract, and response metadata.

Coverage:
  - MindmapFocusSchema validation and coercion
  - apply_mindmap_focus: all filter dimensions (node_id, source_id, source_name,
    page_ref, unit_id, text overlap)
  - Priority order: node_id > source_id > source_name > page_ref > unit_id > text
  - Focus metadata contract (focus_applied, matched_*, filter counts)
  - finalize_retrieved_snippets: metadata 4-tuple return
"""
from __future__ import annotations

from typing import Any

import pytest

from api.schemas import MindmapFocusSchema
from api.services.chat.fast_qa_reasoning_helpers import apply_mindmap_focus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snip(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal snippet dict."""
    return {
        "source_id": "",
        "source_name": "",
        "page_label": "",
        "unit_id": "",
        "node_id": "",
        "id": "",
        "text": "",
        **kwargs,
    }


def _focus(**kwargs: Any) -> MindmapFocusSchema:
    return MindmapFocusSchema(**kwargs)


# ---------------------------------------------------------------------------
# MindmapFocusSchema — validation
# ---------------------------------------------------------------------------

class TestMindmapFocusSchema:
    def test_empty_default(self):
        f = MindmapFocusSchema()
        assert f.node_id == ""
        assert f.source_id == ""
        assert f.source_name == ""
        assert f.page_ref == ""
        assert f.unit_id == ""
        assert f.text == ""
        assert f.is_empty()

    def test_none_input_produces_empty(self):
        f = MindmapFocusSchema.model_validate(None)
        assert f.is_empty()

    def test_dict_input_accepted(self):
        f = MindmapFocusSchema.model_validate({"source_id": "abc-123"})
        assert f.source_id == "abc-123"

    def test_extra_keys_ignored(self):
        # extra="ignore" — unknown keys must not raise
        f = MindmapFocusSchema.model_validate({"source_id": "x", "unknown_field": "y"})
        assert f.source_id == "x"
        assert not hasattr(f, "unknown_field")

    def test_whitespace_coercion(self):
        f = _focus(source_id="  abc  123  ", source_name="\t Q4 Report \n")
        assert f.source_id == "abc 123"
        assert f.source_name == "Q4 Report"

    def test_none_field_coerced_to_empty_string(self):
        f = MindmapFocusSchema.model_validate({"source_id": None, "page_ref": None})
        assert f.source_id == ""
        assert f.page_ref == ""

    def test_is_empty_false_when_any_field_set(self):
        for field in ("node_id", "source_id", "source_name", "page_ref", "unit_id", "text"):
            f = MindmapFocusSchema.model_validate({field: "x"})
            assert not f.is_empty(), f"is_empty() should be False when {field}='x'"

    def test_model_dump_roundtrip(self):
        f = _focus(source_id="s1", page_ref="3", text="hello world")
        d = f.model_dump()
        assert d["source_id"] == "s1"
        assert d["page_ref"] == "3"
        assert d["text"] == "hello world"
        assert d["node_id"] == ""


# ---------------------------------------------------------------------------
# apply_mindmap_focus — no focus / empty
# ---------------------------------------------------------------------------

class TestApplyMindmapFocusNoFilter:
    def test_returns_original_when_focus_is_none(self):
        snippets = [_snip(source_id="s1"), _snip(source_id="s2")]
        result, meta = apply_mindmap_focus(snippets, None)
        assert result == snippets
        assert meta["focus_applied"] is False

    def test_returns_original_when_focus_is_empty_dict(self):
        snippets = [_snip(source_id="s1")]
        result, meta = apply_mindmap_focus(snippets, {})
        assert result == snippets
        assert meta["focus_applied"] is False

    def test_returns_original_when_focus_is_empty_schema(self):
        snippets = [_snip(source_id="s1")]
        result, meta = apply_mindmap_focus(snippets, MindmapFocusSchema())
        assert result == snippets
        assert meta["focus_applied"] is False

    def test_returns_original_when_snippets_empty(self):
        result, meta = apply_mindmap_focus([], _focus(source_id="s1"))
        assert result == []
        assert meta["focus_filter_count_before"] == 0


# ---------------------------------------------------------------------------
# apply_mindmap_focus — node_id (priority 1)
# ---------------------------------------------------------------------------

class TestNodeIdFilter:
    def test_exact_node_id_match_on_node_id_field(self):
        s1 = _snip(node_id="node_abc", source_id="s1")
        s2 = _snip(node_id="node_xyz", source_id="s2")
        result, meta = apply_mindmap_focus([s1, s2], _focus(node_id="node_abc"))
        assert result == [s1]
        assert meta["matched_node_id"] == "node_abc"
        assert meta["focus_applied"] is True

    def test_exact_node_id_match_on_id_field(self):
        s1 = _snip(id="node_abc", source_id="s1")
        s2 = _snip(id="other", source_id="s2")
        result, meta = apply_mindmap_focus([s1, s2], _focus(node_id="node_abc"))
        assert result == [s1]
        assert meta["matched_node_id"] == "node_abc"

    def test_node_id_short_circuits_source_filter(self):
        """node_id match must skip source-level filtering entirely."""
        s1 = _snip(node_id="n1", source_id="wrong_source")
        s2 = _snip(node_id="n2", source_id="correct_source")
        # Provide both node_id and source_id; node_id wins if it matches
        result, meta = apply_mindmap_focus(
            [s1, s2],
            _focus(node_id="n1", source_id="correct_source"),
        )
        assert result == [s1]
        assert meta["matched_node_id"] == "n1"

    def test_node_id_no_match_falls_through_to_source(self):
        """If node_id matches nothing, fall through to source_id filter."""
        s1 = _snip(node_id="other", source_id="s1")
        s2 = _snip(node_id="other2", source_id="s2")
        result, meta = apply_mindmap_focus(
            [s1, s2],
            _focus(node_id="nonexistent", source_id="s1"),
        )
        assert result == [s1]
        assert meta["matched_source_id"] == "s1"


# ---------------------------------------------------------------------------
# apply_mindmap_focus — source_id (priority 2)
# ---------------------------------------------------------------------------

class TestSourceIdFilter:
    def test_exact_source_id_match(self):
        s1 = _snip(source_id="abc")
        s2 = _snip(source_id="xyz")
        result, meta = apply_mindmap_focus([s1, s2], _focus(source_id="abc"))
        assert result == [s1]
        assert meta["matched_source_id"] == "abc"

    def test_source_id_no_match_returns_originals(self):
        s1 = _snip(source_id="abc")
        result, meta = apply_mindmap_focus([s1], _focus(source_id="missing"))
        # No matches → fall through → return originals
        assert result == [s1]

    def test_source_id_takes_priority_over_source_name(self):
        s1 = _snip(source_id="s1", source_name="Report Alpha")
        s2 = _snip(source_id="s2", source_name="Report Alpha")
        result, _ = apply_mindmap_focus([s1, s2], _focus(source_id="s1", source_name="Report Alpha"))
        assert result == [s1]


# ---------------------------------------------------------------------------
# apply_mindmap_focus — source_name (priority 3)
# ---------------------------------------------------------------------------

class TestSourceNameFilter:
    def test_substring_match_case_insensitive(self):
        s1 = _snip(source_name="Q4 Financial Report")
        s2 = _snip(source_name="Roadmap 2025")
        result, _ = apply_mindmap_focus([s1, s2], _focus(source_name="financial"))
        assert result == [s1]

    def test_source_name_no_match_returns_originals(self):
        s1 = _snip(source_name="Roadmap")
        result, _ = apply_mindmap_focus([s1], _focus(source_name="missing_term"))
        assert result == [s1]


# ---------------------------------------------------------------------------
# apply_mindmap_focus — page_ref (priority 4)
# ---------------------------------------------------------------------------

class TestPageRefFilter:
    def test_narrows_within_source_filter(self):
        s1 = _snip(source_id="s1", page_label="5")
        s2 = _snip(source_id="s1", page_label="12")
        result, meta = apply_mindmap_focus([s1, s2], _focus(source_id="s1", page_ref="5"))
        assert result == [s1]
        assert meta["matched_page_ref"] == "5"

    def test_page_ref_no_match_keeps_source_filtered_pool(self):
        s1 = _snip(source_id="s1", page_label="5")
        s2 = _snip(source_id="s1", page_label="12")
        # page_ref has no match → keeps s1+s2 (both from source s1)
        result, meta = apply_mindmap_focus([s1, s2], _focus(source_id="s1", page_ref="99"))
        assert s1 in result and s2 in result
        assert meta["matched_page_ref"] == ""


# ---------------------------------------------------------------------------
# apply_mindmap_focus — unit_id (priority 5)
# ---------------------------------------------------------------------------

class TestUnitIdFilter:
    def test_unit_id_exact_match(self):
        s1 = _snip(source_id="s1", unit_id="section_3")
        s2 = _snip(source_id="s1", unit_id="section_7")
        result, _ = apply_mindmap_focus([s1, s2], _focus(source_id="s1", unit_id="section_3"))
        assert result == [s1]


# ---------------------------------------------------------------------------
# apply_mindmap_focus — text overlap (priority 6)
# ---------------------------------------------------------------------------

class TestTextOverlapRanking:
    def test_high_overlap_ranked_first(self):
        s1 = _snip(text="revenue growth EBITDA margin quarterly results")
        s2 = _snip(text="employee headcount HR policies")
        s3 = _snip(text="EBITDA revenue Q4 financial results")
        result, _ = apply_mindmap_focus([s2, s1, s3], _focus(text="EBITDA revenue quarterly"))
        # s1 and s3 have high overlap; s2 should be last or excluded
        assert result[0] in (s1, s3)
        assert s2 not in result or result.index(s2) > result.index(s1)

    def test_zero_overlap_returns_all(self):
        s1 = _snip(text="completely unrelated content here")
        result, _ = apply_mindmap_focus([s1], _focus(text="xyz zyx zzz"))
        # No overlap → original list returned unchanged
        assert result == [s1]


# ---------------------------------------------------------------------------
# Focus metadata contract
# ---------------------------------------------------------------------------

class TestFocusMetadata:
    def test_focus_applied_false_when_no_focus(self):
        _, meta = apply_mindmap_focus([_snip()], None)
        assert meta["focus_applied"] is False
        assert meta["matched_node_id"] == ""
        assert meta["matched_source_id"] == ""
        assert meta["matched_page_ref"] == ""

    def test_focus_applied_true_when_source_id_matches(self):
        s = _snip(source_id="s1")
        _, meta = apply_mindmap_focus([s], _focus(source_id="s1"))
        assert meta["focus_applied"] is True
        assert meta["matched_source_id"] == "s1"

    def test_filter_counts_reflect_reduction(self):
        snippets = [_snip(source_id="s1"), _snip(source_id="s2"), _snip(source_id="s2")]
        _, meta = apply_mindmap_focus(snippets, _focus(source_id="s2"))
        assert meta["focus_filter_count_before"] == 3
        assert meta["focus_filter_count_after"] == 2

    def test_node_id_meta_populated(self):
        s = _snip(node_id="n1")
        _, meta = apply_mindmap_focus([s], _focus(node_id="n1"))
        assert meta["matched_node_id"] == "n1"
        assert meta["focus_filter_count_after"] == 1

    def test_page_ref_meta_populated(self):
        s = _snip(source_id="s1", page_label="7")
        _, meta = apply_mindmap_focus([s], _focus(source_id="s1", page_ref="7"))
        assert meta["matched_page_ref"] == "7"


# ---------------------------------------------------------------------------
# finalize_retrieved_snippets — 4-tuple return + metadata threading
# ---------------------------------------------------------------------------

class TestFinalizeReturnContract:
    """Verify finalize_retrieved_snippets returns a 4-tuple including focus_meta."""

    def _make_finalize_fn(self):
        from api.services.chat.fast_qa_reasoning_helpers import finalize_retrieved_snippets

        def _annotate(question, snippets, selected_payload, target_urls):
            return snippets, ""

        def _apply(snippets, focus):
            return apply_mindmap_focus(snippets, focus)

        def _score(row):
            return 1.0

        def _llm_select(question, chat_history, snippets, max_keep):
            return snippets[:max_keep]

        def _prioritize(pool, max_keep, max_secondary=0):
            return pool[:max_keep]

        def call(snippets, focus):
            return finalize_retrieved_snippets(
                question="test question",
                chat_history=[],
                retrieved_snippets=snippets,
                selected_payload={},
                target_urls=[],
                mindmap_focus=focus,
                max_keep=10,
                annotate_primary_sources_fn=_annotate,
                apply_mindmap_focus_fn=_apply,
                snippet_score_fn=_score,
                select_relevant_snippets_with_llm_fn=_llm_select,
                prioritize_primary_evidence_fn=_prioritize,
            )

        return call

    def test_returns_four_tuple(self):
        fn = self._make_finalize_fn()
        result = fn([_snip(source_id="s1")], MindmapFocusSchema())
        assert len(result) == 4, "finalize_retrieved_snippets must return a 4-tuple"

    def test_fourth_element_is_dict(self):
        fn = self._make_finalize_fn()
        _, _, _, meta = fn([_snip(source_id="s1")], MindmapFocusSchema())
        assert isinstance(meta, dict)
        assert "focus_applied" in meta
        assert "focus_filter_count_before" in meta
        assert "focus_filter_count_after" in meta

    def test_empty_snippets_returns_no_focus_meta(self):
        fn = self._make_finalize_fn()
        _, _, reason, meta = fn([], _focus(source_id="s1"))
        assert reason == "no_snippets"
        assert meta["focus_applied"] is False

    def test_focus_meta_reflects_filter_when_source_id_set(self):
        fn = self._make_finalize_fn()
        snippets = [_snip(source_id="s1"), _snip(source_id="s2")]
        _, _, _, meta = fn(snippets, _focus(source_id="s1"))
        assert meta["focus_applied"] is True
        assert meta["matched_source_id"] == "s1"
        assert meta["focus_filter_count_before"] == 2
        assert meta["focus_filter_count_after"] == 1
