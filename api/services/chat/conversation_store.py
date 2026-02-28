from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select
from tzlocal import get_localzone

from ktem.db.models import Conversation, engine

from api.context import ApiContext


def get_or_create_conversation(
    user_id: str,
    conversation_id: str | None,
) -> tuple[str, str, dict[str, Any]]:
    with Session(engine) as session:
        if conversation_id:
            conv = session.exec(
                select(Conversation).where(Conversation.id == conversation_id)
            ).first()
            if conv is None:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            if conv.user != user_id and not conv.is_public:
                raise HTTPException(status_code=403, detail="Access denied.")
            return conv.id, conv.name, deepcopy(conv.data_source or {})

        conv = Conversation(user=user_id)
        session.add(conv)
        session.commit()
        session.refresh(conv)
        return conv.id, conv.name, {}


def build_selected_payload(
    context: ApiContext,
    user_id: str,
    existing_selected: dict[str, Any],
    requested_selected: dict[str, Any],
) -> dict[str, list[Any]]:
    payload: dict[str, list[Any]] = {}

    for idx, index in enumerate(context.app.index_manager.indices):
        key = str(index.id)

        mode = "all" if idx == 0 else "disabled"
        selected_ids: list[str] = []

        existing = existing_selected.get(key)
        if isinstance(existing, list) and len(existing) >= 2:
            if isinstance(existing[0], str):
                mode = existing[0]
            if isinstance(existing[1], list):
                selected_ids = [str(item) for item in existing[1]]

        requested = requested_selected.get(key)
        if requested is not None:
            mode = requested.mode
            selected_ids = [str(item) for item in requested.file_ids]

        payload[key] = [mode, selected_ids, user_id]

    return payload


def persist_conversation(
    conversation_id: str,
    payload: dict[str, Any],
) -> None:
    with Session(engine) as session:
        conv = session.exec(
            select(Conversation).where(Conversation.id == conversation_id)
        ).first()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        conv.data_source = payload
        conv.date_updated = datetime.now(get_localzone())
        session.add(conv)
        session.commit()
