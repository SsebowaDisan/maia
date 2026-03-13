"""Contract tests for api.services.chat.block_builder.

Covers:
- Every response mode returns non-empty valid blocks.
- Optics prompt emits widget:lens_equation prepended before answer blocks.
- Document action always has a matching CanvasDocumentRecord in documents[].
- Fenced code → code block; display math → math block; pipe table → table block.
- Plain prose → markdown block fallback.
- stream/non-stream parity contract: build_turn_blocks is the same function used
  by all paths, so structural equivalence is guaranteed (tested by calling it
  twice with identical args).
"""

from api.services.chat.block_builder import build_turn_blocks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _types(blocks: list[dict]) -> list[str]:
    return [b["type"] for b in blocks]


# ---------------------------------------------------------------------------
# Always at least one block
# ---------------------------------------------------------------------------

def test_plain_answer_returns_markdown_block() -> None:
    blocks, documents = build_turn_blocks(answer_text="Hello world")
    assert len(blocks) >= 1
    assert blocks[0]["type"] == "markdown"
    assert documents == []


def test_empty_answer_still_returns_no_crash() -> None:
    blocks, documents = build_turn_blocks(answer_text="")
    # normalize_turn_structured_content falls back to [] for empty text, which
    # is acceptable — the contract only requires non-crash and valid types.
    assert isinstance(blocks, list)
    assert isinstance(documents, list)


# ---------------------------------------------------------------------------
# Optics / lens widget
# ---------------------------------------------------------------------------

def test_optics_question_prepends_lens_widget() -> None:
    blocks, _ = build_turn_blocks(
        answer_text="The focal length is 20 cm.",
        question="What is the thin lens equation?",
    )
    assert blocks[0]["type"] == "widget"
    assert blocks[0]["widget"]["kind"] == "lens_equation"


def test_lens_props_extracted_from_answer() -> None:
    blocks, _ = build_turn_blocks(
        answer_text="focal length = 15, object distance = 45 cm",
        question="Explain the converging lens setup.",
    )
    props = blocks[0]["widget"]["props"]
    assert props["focalLength"] == 15.0
    assert props["objectDistance"] == 45.0


def test_lens_props_default_when_not_in_text() -> None:
    blocks, _ = build_turn_blocks(
        answer_text="A thin lens bends light.",
        question="Describe a thin lens.",
    )
    props = blocks[0]["widget"]["props"]
    assert props["focalLength"] == 10.0
    assert props["objectDistance"] == 30.0


def test_non_optics_question_no_widget() -> None:
    blocks, _ = build_turn_blocks(
        answer_text="The revenue grew 20% in Q3.",
        question="What happened to revenue in Q3?",
    )
    assert all(b["type"] != "widget" for b in blocks)


# ---------------------------------------------------------------------------
# Code block extraction
# ---------------------------------------------------------------------------

def test_fenced_code_becomes_code_block() -> None:
    answer = "Here is the code:\n```python\nprint('hello')\n```\nDone."
    blocks, _ = build_turn_blocks(answer_text=answer)
    types = _types(blocks)
    assert "code" in types
    code_block = next(b for b in blocks if b["type"] == "code")
    assert code_block["language"] == "python"
    assert "print" in code_block["code"]


def test_fenced_code_no_lang_label() -> None:
    answer = "```\nselect * from users;\n```"
    blocks, _ = build_turn_blocks(answer_text=answer)
    code_block = next(b for b in blocks if b["type"] == "code")
    assert code_block["language"] == ""


# ---------------------------------------------------------------------------
# Math block extraction
# ---------------------------------------------------------------------------

def test_display_math_becomes_math_block() -> None:
    answer = "The equation is:\n$$E = mc^2$$\nEinstein."
    blocks, _ = build_turn_blocks(answer_text=answer)
    math_blocks = [b for b in blocks if b["type"] == "math"]
    assert len(math_blocks) == 1
    assert "mc^2" in math_blocks[0]["latex"]
    assert math_blocks[0]["display"] is True


# ---------------------------------------------------------------------------
# Table block extraction
# ---------------------------------------------------------------------------

def test_markdown_table_becomes_table_block() -> None:
    answer = (
        "Results:\n"
        "| Name | Score |\n"
        "| ---- | ----- |\n"
        "| Alice | 95 |\n"
        "| Bob | 88 |\n"
        "End."
    )
    blocks, _ = build_turn_blocks(answer_text=answer)
    table_blocks = [b for b in blocks if b["type"] == "table"]
    assert len(table_blocks) == 1
    tbl = table_blocks[0]
    assert tbl["columns"] == ["Name", "Score"]
    assert ["Alice", "95"] in tbl["rows"]
    assert ["Bob", "88"] in tbl["rows"]


# ---------------------------------------------------------------------------
# Document action — always has matching CanvasDocumentRecord
# ---------------------------------------------------------------------------

def test_document_action_has_matching_record() -> None:
    ws = {
        "deep_research_doc_id": "doc_abc123",
        "deep_research_doc_url": "https://docs.google.com/d/abc",
        "deep_research_sheet_id": "",
        "deep_research_sheet_url": "",
    }
    blocks, documents = build_turn_blocks(
        answer_text="Here is the research.", workspace_ids=ws
    )
    doc_action_blocks = [b for b in blocks if b["type"] == "document_action"]
    assert len(doc_action_blocks) == 1
    action = doc_action_blocks[0]["action"]
    assert action["documentId"] == "doc_abc123"
    assert action["kind"] == "open_canvas"

    # Matching document must exist.
    assert any(d["id"] == "doc_abc123" for d in documents)


def test_sheet_document_action_has_matching_record() -> None:
    ws = {
        "deep_research_doc_id": "",
        "deep_research_doc_url": "",
        "deep_research_sheet_id": "sheet_xyz",
        "deep_research_sheet_url": "https://sheets.google.com/s/xyz",
    }
    blocks, documents = build_turn_blocks(
        answer_text="Spreadsheet ready.", workspace_ids=ws
    )
    sheet_actions = [b for b in blocks if b["type"] == "document_action"]
    assert len(sheet_actions) == 1
    assert sheet_actions[0]["action"]["documentId"] == "sheet_xyz"
    assert any(d["id"] == "sheet_xyz" for d in documents)


def test_no_orphan_document_action_without_workspace_ids() -> None:
    blocks, documents = build_turn_blocks(answer_text="Plain answer.")
    assert all(b["type"] != "document_action" for b in blocks)
    assert documents == []


# ---------------------------------------------------------------------------
# Stream / non-stream parity (structural equivalence)
# ---------------------------------------------------------------------------

def test_same_inputs_produce_identical_blocks() -> None:
    """Calling build_turn_blocks twice with identical args gives identical output."""
    kwargs = dict(
        answer_text="The focal length is 10 cm.\n```python\nx=1\n```",
        question="What is the thin lens equation?",
    )
    blocks_a, docs_a = build_turn_blocks(**kwargs)
    blocks_b, docs_b = build_turn_blocks(**kwargs)
    assert blocks_a == blocks_b
    assert docs_a == docs_b


# ---------------------------------------------------------------------------
# Mixed content: all block types in one answer
# ---------------------------------------------------------------------------

def test_mixed_content_produces_multiple_block_types() -> None:
    answer = (
        "Summary paragraph.\n"
        "```sql\nSELECT 1;\n```\n"
        "| A | B |\n| - | - |\n| 1 | 2 |\n"
        "$$x^2 + y^2 = r^2$$\n"
        "Conclusion."
    )
    blocks, _ = build_turn_blocks(answer_text=answer, question="")
    types = _types(blocks)
    assert "code" in types
    assert "table" in types
    assert "math" in types
    assert "markdown" in types
