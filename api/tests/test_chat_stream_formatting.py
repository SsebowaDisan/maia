from api.services.chat_service import _chunk_text_for_stream


def test_chunk_text_for_stream_preserves_markdown_newlines() -> None:
    text = "## Execution Plan\n1. Inspect website\n2. Send report\n\n## Delivery Status\n- Sent"
    chunks = _chunk_text_for_stream(text, chunk_size=16)

    assert chunks
    assert "".join(chunks) == text
