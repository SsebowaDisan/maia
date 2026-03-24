"""P9-03 — Canvas document store.

Responsibility: persist Canvas documents (title + markdown content) per tenant.
Used by agents (via canvas.create_document tool) and by the Canvas panel in the
frontend (via REST).

Documents are stored in a SQLite table and served through the existing
CanvasDocumentRecord schema so the frontend canvasStore can consume them.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine
from sqlalchemy import text


class CanvasDocument(SQLModel, table=True):
    __tablename__ = "maia_canvas_document"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    title: str = ""
    content: str = ""
    info_html: str = ""
    info_panel_json: str = ""
    user_prompt: str = ""
    mode_variant: str = ""
    source_agent_id: str = ""
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        columns = {
            str(row[1]).strip().lower()
            for row in connection.exec_driver_sql(
                "PRAGMA table_info('maia_canvas_document')"
            ).fetchall()
        }
        if "info_html" not in columns:
            connection.execute(
                text("ALTER TABLE maia_canvas_document ADD COLUMN info_html TEXT DEFAULT ''")
            )
        if "user_prompt" not in columns:
            connection.execute(
                text("ALTER TABLE maia_canvas_document ADD COLUMN user_prompt TEXT DEFAULT ''")
            )
        if "info_panel_json" not in columns:
            connection.execute(
                text("ALTER TABLE maia_canvas_document ADD COLUMN info_panel_json TEXT DEFAULT ''")
            )
        if "mode_variant" not in columns:
            connection.execute(
                text("ALTER TABLE maia_canvas_document ADD COLUMN mode_variant TEXT DEFAULT ''")
            )


# ── Public API ─────────────────────────────────────────────────────────────────

def create_document(
    tenant_id: str,
    title: str,
    content: str = "",
    *,
    info_html: str = "",
    info_panel: dict[str, Any] | None = None,
    user_prompt: str = "",
    mode_variant: str = "",
    source_agent_id: str = "",
) -> CanvasDocument:
    _ensure_tables()
    doc = CanvasDocument(
        tenant_id=tenant_id,
        title=title.strip() or "Untitled document",
        content=content,
        info_html=info_html,
        info_panel_json=json.dumps(info_panel or {}, ensure_ascii=False),
        user_prompt=user_prompt,
        mode_variant=mode_variant,
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
    info_html: str | None = None,
    info_panel: dict[str, Any] | None = None,
    user_prompt: str | None = None,
    mode_variant: str | None = None,
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
        if info_html is not None:
            doc.info_html = info_html
        if info_panel is not None:
            doc.info_panel_json = json.dumps(info_panel, ensure_ascii=False)
        if user_prompt is not None:
            doc.user_prompt = user_prompt
        if mode_variant is not None:
            doc.mode_variant = mode_variant
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
    try:
        info_panel = json.loads(str(doc.info_panel_json or "").strip() or "{}")
        if not isinstance(info_panel, dict):
            info_panel = {}
    except Exception:
        info_panel = {}
    return {
        "id": doc.id,
        "title": doc.title,
        "content": doc.content,
        "info_html": doc.info_html,
        "info_panel": info_panel,
        "user_prompt": doc.user_prompt,
        "mode_variant": doc.mode_variant,
        "source_agent_id": doc.source_agent_id,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }
