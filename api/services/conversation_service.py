from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select
from tzlocal import get_localzone

from ktem.db.models import Conversation, engine
from api.services.chat.conversation_naming import (
    extract_conversation_icon,
    generate_conversation_name,
    is_placeholder_conversation_name,
    normalize_conversation_name,
)

AUTONAME_BACKFILL_LIMIT = 8


def _first_user_message(data_source: dict) -> str:
    messages = data_source.get("messages", [])
    if not isinstance(messages, list):
        return ""
    for item in messages:
        if not isinstance(item, (list, tuple)) or not item:
            continue
        text = str(item[0] or "").strip()
        if text:
            return text
    return ""


def _agent_mode_from_state(data_source: dict) -> str:
    state = data_source.get("state")
    if isinstance(state, dict):
        mode = str(state.get("mode") or "").strip()
        if mode:
            return mode
    return "ask"


def _to_summary(conv: Conversation) -> dict:
    data_source = conv.data_source or {}
    messages = data_source.get("messages", [])
    return {
        "id": conv.id,
        "name": normalize_conversation_name(conv.name),
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

        backfilled = 0
        for row in rows:
            if backfilled >= AUTONAME_BACKFILL_LIMIT:
                break
            if not is_placeholder_conversation_name(row.name):
                continue
            data_source = row.data_source or {}
            first_message = _first_user_message(data_source)
            if not first_message:
                continue
            row.name = generate_conversation_name(
                first_message,
                agent_mode=_agent_mode_from_state(data_source),
            )
            row.date_updated = datetime.now(get_localzone())
            session.add(row)
            backfilled += 1

        if backfilled:
            session.commit()
    return [_to_summary(row) for row in rows]


def create_conversation(user_id: str, name: str | None, is_public: bool) -> dict:
    with Session(engine) as session:
        conv = Conversation(user=user_id)
        conv.name = normalize_conversation_name(str(name or ""), icon=extract_conversation_icon(conv.name))
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
            conv.name = normalize_conversation_name(
                name,
                icon=extract_conversation_icon(conv.name),
            )
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
