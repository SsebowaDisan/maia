from __future__ import annotations

from copy import deepcopy
from typing import Any

from api.services.canvas.document_store import create_document, document_to_dict

from .fast_qa_turn_sections.common import derive_rag_canvas_title


def attach_canvas_document(
    *,
    user_id: str,
    question: str,
    answer_text: str,
    info_html: str,
    info_panel: dict[str, Any],
    mode_variant: str,
    source_agent_id: str = "",
    blocks: list[dict[str, Any]] | None = None,
    documents: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    answer = str(answer_text or "")
    if not answer.strip():
        return list(blocks or []), list(documents or []), None

    canvas_title = derive_rag_canvas_title(question, answer)
    canvas_document = create_document(
        tenant_id=user_id,
        title=canvas_title,
        content=answer,
        info_html=info_html,
        info_panel=deepcopy(info_panel),
        user_prompt=question,
        mode_variant=str(mode_variant or "").strip(),
        source_agent_id=str(source_agent_id or "").strip(),
    )
    canvas_payload = document_to_dict(canvas_document)
    canvas_document_id = str(canvas_payload.get("id") or "").strip()
    if not canvas_document_id:
        return list(blocks or []), list(documents or []), None

    merged_documents: list[dict[str, Any]] = [canvas_payload]
    for row in list(documents or []):
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id") or "").strip()
        if row_id and row_id != canvas_document_id:
            merged_documents.append(row)

    merged_blocks = list(blocks or [])
    has_canvas_action = any(
        isinstance(block, dict)
        and str(block.get("type") or "").strip().lower() == "document_action"
        and str((block.get("action") or {}).get("documentId") or "").strip() == canvas_document_id
        for block in merged_blocks
    )
    if not has_canvas_action:
        merged_blocks.insert(
            0,
            {
                "type": "document_action",
                "action": {
                    "kind": "open_canvas",
                    "title": str(canvas_payload.get("title") or canvas_title),
                    "documentId": canvas_document_id,
                },
            },
        )

    return merged_blocks, merged_documents, canvas_payload

