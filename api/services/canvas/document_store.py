"""P9-03 — Canvas document store.

Responsibility: persist Canvas documents (title + markdown content) per tenant.
Used by agents (via canvas.create_document tool) and by the Canvas panel in the
frontend (via REST).

Documents are stored in a SQLite table and served through the existing
CanvasDocumentRecord schema so the frontend canvasStore can consume them.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine


class CanvasDocument(SQLModel, table=True):
    __tablename__ = "maia_canvas_document"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    title: str = ""
    content: str = ""
    source_agent_id: str = ""
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ── Public API ─────────────────────────────────────────────────────────────────

def create_document(
    tenant_id: str,
    title: str,
    content: str = "",
    *,
    source_agent_id: str = "",
) -> CanvasDocument:
    _ensure_tables()
    doc = CanvasDocument(
        tenant_id=tenant_id,
        title=title.strip() or "Untitled document",
        content=content,
        source_agent_id=source_agent_id,
    )
    with Session(engine) as session:
        session.add(doc)
        session.commit()
        session.refresh(doc)
    return doc


def get_document(tenant_id: str, document_id: str) -> CanvasDocument | None:
    _ensure_tables()
    with Session(engine) as session:
        doc = session.get(CanvasDocument, document_id)
    if not doc or doc.tenant_id != tenant_id:
        return None
    return doc


def list_documents(tenant_id: str, limit: int = 50) -> Sequence[CanvasDocument]:
    _ensure_tables()
    with Session(engine) as session:
        return session.exec(
            select(CanvasDocument)
            .where(CanvasDocument.tenant_id == tenant_id)
            .order_by(CanvasDocument.updated_at.desc())  # type: ignore[arg-type]
            .limit(limit)
        ).all()


def update_document(
    tenant_id: str,
    document_id: str,
    *,
    title: str | None = None,
    content: str | None = None,
) -> CanvasDocument | None:
    _ensure_tables()
    with Session(engine) as session:
        doc = session.get(CanvasDocument, document_id)
        if not doc or doc.tenant_id != tenant_id:
            return None
        if title is not None:
            doc.title = title.strip() or doc.title
        if content is not None:
            doc.content = content
        doc.updated_at = time.time()
        session.add(doc)
        session.commit()
        session.refresh(doc)
    return doc


def delete_document(tenant_id: str, document_id: str) -> bool:
    _ensure_tables()
    with Session(engine) as session:
        doc = session.get(CanvasDocument, document_id)
        if not doc or doc.tenant_id != tenant_id:
            return False
        session.delete(doc)
        session.commit()
    return True


def document_to_dict(doc: CanvasDocument) -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "content": doc.content,
        "source_agent_id": doc.source_agent_id,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }
