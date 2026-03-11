from api.message_blocks import (
    default_answer_blocks,
    normalize_canvas_documents,
    normalize_message_blocks,
    normalize_turn_structured_content,
)


def test_default_answer_blocks_wrap_answer_as_markdown() -> None:
    assert default_answer_blocks("Hello") == [{"type": "markdown", "markdown": "Hello"}]


def test_normalize_message_blocks_falls_back_on_invalid_payload() -> None:
    assert normalize_message_blocks([{"type": "widget"}], answer_text="Fallback") == [
        {"type": "markdown", "markdown": "Fallback"}
    ]


def test_normalize_message_blocks_keeps_valid_widget_payload() -> None:
    assert normalize_message_blocks(
        [
            {
                "type": "widget",
                "widget": {
                    "kind": "lens_equation",
                    "props": {"focalLength": 10, "objectDistance": 30},
                },
            }
        ]
    ) == [
        {
            "type": "widget",
            "widget": {
                "kind": "lens_equation",
                "props": {"focalLength": 10, "objectDistance": 30},
            },
        }
    ]


def test_normalize_canvas_documents_filters_invalid_rows() -> None:
    assert normalize_canvas_documents(
        [
            {"id": "doc_1", "title": "Lens report", "content": "# Draft"},
            {"id": "", "title": "Broken"},
        ]
    ) == [{"id": "doc_1", "title": "Lens report", "content": "# Draft"}]


def test_normalize_turn_structured_content_returns_blocks_and_documents() -> None:
    blocks, documents = normalize_turn_structured_content(
        answer_text="Fallback",
        blocks=[{"type": "text", "text": "Hi"}],
        documents=[{"id": "doc_1", "title": "Draft", "content": "# Note"}],
    )

    assert blocks == [{"type": "text", "text": "Hi"}]
    assert documents == [{"id": "doc_1", "title": "Draft", "content": "# Note"}]
