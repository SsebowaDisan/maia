from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select
from tzlocal import get_localzone

from ktem.db.models import Conversation, engine


def _to_summary(conv: Conversation) -> dict:
    data_source = conv.data_source or {}
    messages = data_source.get("messages", [])
    return {
        "id": conv.id,
        "name": conv.name,
        "user": conv.user,
        "is_public": conv.is_public,
        "date_created": conv.date_created,
        "date_updated": conv.date_updated,
        "message_count": len(messages),
    }


def list_conversations(user_id: str) -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(
            select(Conversation)
            .where(Conversation.user == user_id)
            .order_by(Conversation.date_updated.desc())  # type: ignore[attr-defined]
        ).all()
    return [_to_summary(row) for row in rows]


def create_conversation(user_id: str, name: str | None, is_public: bool) -> dict:
    with Session(engine) as session:
        conv = Conversation(user=user_id)
        if name:
            conv.name = name
        conv.is_public = is_public
        session.add(conv)
        session.commit()
        session.refresh(conv)

    payload = _to_summary(conv)
    payload["data_source"] = deepcopy(conv.data_source or {})
    return payload


def get_conversation(user_id: str, conversation_id: str) -> dict:
    with Session(engine) as session:
        conv = session.exec(
            select(Conversation).where(Conversation.id == conversation_id)
        ).first()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        if conv.user != user_id and not conv.is_public:
            raise HTTPException(status_code=403, detail="Access denied.")

    payload = _to_summary(conv)
    payload["data_source"] = deepcopy(conv.data_source or {})
    return payload


def update_conversation(
    user_id: str,
    conversation_id: str,
    name: str | None,
    is_public: bool | None,
) -> dict:
    with Session(engine) as session:
        conv = session.exec(
            select(Conversation).where(Conversation.id == conversation_id)
        ).first()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        if conv.user != user_id:
            raise HTTPException(status_code=403, detail="Only owner can update.")

        if name is not None:
            conv.name = name
        if is_public is not None:
            conv.is_public = is_public
        conv.date_updated = datetime.now(get_localzone())
        session.add(conv)
        session.commit()
        session.refresh(conv)

    payload = _to_summary(conv)
    payload["data_source"] = deepcopy(conv.data_source or {})
    return payload


def delete_conversation(user_id: str, conversation_id: str) -> None:
    with Session(engine) as session:
        conv = session.exec(
            select(Conversation).where(Conversation.id == conversation_id)
        ).first()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        if conv.user != user_id:
            raise HTTPException(status_code=403, detail="Only owner can delete.")
        session.delete(conv)
        session.commit()

