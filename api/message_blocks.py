from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, Field, TypeAdapter, ValidationError


class TextBlock(BaseModel):
    type: Literal["text"]
    text: str


class MarkdownBlock(BaseModel):
    type: Literal["markdown"]
    markdown: str


class MathBlock(BaseModel):
    type: Literal["math"]
    latex: str
    display: bool = False


class CodeBlock(BaseModel):
    type: Literal["code"]
    language: str = ""
    code: str


class ImageBlock(BaseModel):
    type: Literal["image"]
    src: str
    alt: str | None = None


class TableBlock(BaseModel):
    type: Literal["table"]
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class NoticeBlock(BaseModel):
    type: Literal["notice"]
    level: Literal["info", "warning", "error"] = "info"
    text: str


class WidgetDescriptor(BaseModel):
    kind: str
    props: dict[str, Any] = Field(default_factory=dict)


class WidgetBlock(BaseModel):
    type: Literal["widget"]
    widget: WidgetDescriptor = Field(default_factory=WidgetDescriptor)


class DocumentActionDescriptor(BaseModel):
    kind: str
    title: str
    documentId: str


class DocumentActionBlock(BaseModel):
    type: Literal["document_action"]
    action: DocumentActionDescriptor = Field(default_factory=DocumentActionDescriptor)


MessageBlock = Annotated[
    TextBlock
    | MarkdownBlock
    | MathBlock
    | CodeBlock
    | ImageBlock
    | TableBlock
    | NoticeBlock
    | WidgetBlock
    | DocumentActionBlock,
    Field(discriminator="type"),
]


class CanvasDocumentRecord(BaseModel):
    id: str
    title: str
    content: str = ""


_MESSAGE_BLOCKS_ADAPTER = TypeAdapter(list[MessageBlock])
_CANVAS_DOCUMENTS_ADAPTER = TypeAdapter(list[CanvasDocumentRecord])


def _model_list_dump(items: list[Any]) -> list[dict[str, Any]]:
    return [cast(BaseModel, item).model_dump(mode="python") for item in items]


def default_answer_blocks(answer_text: str) -> list[dict[str, Any]]:
    text = str(answer_text or "").strip()
    if not text:
        return []
    return [{"type": "markdown", "markdown": text}]


def normalize_message_blocks(raw: Any, *, answer_text: str = "") -> list[dict[str, Any]]:
    if raw is None:
        return default_answer_blocks(answer_text)
    try:
        parsed = _MESSAGE_BLOCKS_ADAPTER.validate_python(raw)
    except ValidationError:
        return default_answer_blocks(answer_text)
    dumped = _model_list_dump(parsed)
    return dumped or default_answer_blocks(answer_text)


def normalize_canvas_documents(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    try:
        parsed = _CANVAS_DOCUMENTS_ADAPTER.validate_python(raw)
    except ValidationError:
        return []
    return [
        item
        for item in _model_list_dump(parsed)
        if str(item.get("id") or "").strip() and str(item.get("title") or "").strip()
    ]


def normalize_turn_structured_content(
    *,
    answer_text: str,
    blocks: Any = None,
    documents: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        normalize_message_blocks(blocks, answer_text=answer_text),
        normalize_canvas_documents(documents),
    )
