from maia.indices.qa.citation_qa_inline import AnswerWithInlineCitation, InlineEvidence


def _pipeline() -> AnswerWithInlineCitation:
    return object.__new__(AnswerWithInlineCitation)


def test_inline_citation_numbers_are_renumbered_and_deduped() -> None:
    pipeline = _pipeline()
    citations = [
        InlineEvidence(idx=3, start_phrase="a", end_phrase="b"),
        InlineEvidence(idx=1, start_phrase="c", end_phrase="d"),
        InlineEvidence(idx=2, start_phrase="e", end_phrase="f"),
    ]
    answer = "One【3】 Two【1】 Three【2】 Again【3】"

    normalized, mapping = pipeline._normalize_citation_mapping(answer, citations)
    assert mapping == {3: 1, 1: 2, 2: 3}

    for evidence_pos, evidence in enumerate(citations):
        evidence_idx = evidence.idx if evidence.idx is not None else evidence_pos + 1
        evidence.idx = mapping.get(evidence_idx, evidence_idx)

    remapped = pipeline._apply_citation_mapping(normalized, mapping)
    assert remapped == "One【1】 Two【2】 Three【3】 Again【1】"

    rendered = pipeline.replace_citation_with_link(remapped)
    assert rendered.count("class='citation'") == 3
    assert rendered.count("id='mark-1'") == 1
    assert rendered.count("id='mark-2'") == 1
    assert rendered.count("id='mark-3'") == 1


def test_inline_citation_numbers_start_at_one() -> None:
    pipeline = _pipeline()
    citations = [InlineEvidence(idx=2, start_phrase="a", end_phrase="b")]
    answer = "Claim【2】."

    normalized, mapping = pipeline._normalize_citation_mapping(answer, citations)
    remapped = pipeline._apply_citation_mapping(normalized, mapping)
    rendered = pipeline.replace_citation_with_link(remapped)

    assert mapping == {2: 1}
    assert "【1】" in remapped
    assert "id='mark-1'" in rendered
    assert "id='mark-2'" not in rendered


def test_inline_citation_normalization_handles_merged_and_ascii_markers() -> None:
    pipeline = _pipeline()
    citations = [
        InlineEvidence(idx=4, start_phrase="a", end_phrase="b"),
        InlineEvidence(idx=2, start_phrase="c", end_phrase="d"),
    ]
    answer = "A【4, 2】 B[2] C【4】"

    normalized, mapping = pipeline._normalize_citation_mapping(answer, citations)
    remapped = pipeline._apply_citation_mapping(normalized, mapping)
    rendered = pipeline.replace_citation_with_link(remapped)

    assert normalized == "A【4】【2】 B【2】 C【4】"
    assert mapping == {4: 1, 2: 2}
    assert remapped == "A【1】【2】 B【2】 C【1】"
    assert rendered.count("class='citation'") == 2
    assert rendered.count("id='mark-1'") == 1
    assert rendered.count("id='mark-2'") == 1


def test_inline_citation_mapping_keeps_unreferenced_evidence_sequential() -> None:
    pipeline = _pipeline()
    citations = [
        InlineEvidence(idx=3, start_phrase="a", end_phrase="b"),
        InlineEvidence(idx=8, start_phrase="c", end_phrase="d"),
    ]
    answer = "Only one appears【3】."

    _normalized, mapping = pipeline._normalize_citation_mapping(answer, citations)
    assert mapping == {3: 1, 8: 2}
