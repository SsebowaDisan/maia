"""Canvas document REST router.

Routes:
    GET    /api/documents              list canvas documents for tenant
    POST   /api/documents              create a new document
    GET    /api/documents/{id}         get a document
    PUT    /api/documents/{id}         update title/content
    DELETE /api/documents/{id}         delete (204)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import get_current_user_id
from api.services.canvas.document_store import (
    create_document,
    delete_document,
    document_to_dict,
    get_document,
    list_documents,
    update_document,
)

router = APIRouter(prefix="/api/documents", tags=["canvas"])


class CreateDocumentRequest(BaseModel):
    title: str
    content: str = ""


class UpdateDocumentRequest(BaseModel):
    title: str | None = None
    content: str | None = None


@router.get("")
def list_canvas_documents(
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    docs = list_documents(user_id, limit=limit)
    return [document_to_dict(d) for d in docs]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_canvas_document(
    body: CreateDocumentRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    doc = create_document(user_id, body.title, body.content)
    return document_to_dict(doc)


@router.get("/{document_id}")
def get_canvas_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    doc = get_document(user_id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document_to_dict(doc)


@router.put("/{document_id}")
def update_canvas_document(
    document_id: str,
    body: UpdateDocumentRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    doc = update_document(user_id, document_id, title=body.title, content=body.content)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document_to_dict(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_canvas_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
) -> None:
    if not delete_document(user_id, document_id):
        raise HTTPException(status_code=404, detail="Document not found.")
