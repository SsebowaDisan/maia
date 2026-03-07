from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select
from tzlocal import get_localzone

from ktem.db.models import Conversation, engine

from api.context import ApiContext
from api.services.chat.conversation_naming import (
    CONVERSATION_ICON_REVIEWED_FIELD,
    CONVERSATION_ICON_KEY_FIELD,
    DEFAULT_CONVERSATION_ICON_KEY,
    generate_conversation_identity,
    infer_conversation_icon_key,
    is_placeholder_conversation_name,
    normalize_conversation_name,
    normalize_conversation_icon_key,
)

PRESERVED_DATA_SOURCE_KEYS = {
    CONVERSATION_ICON_KEY_FIELD,
    CONVERSATION_ICON_REVIEWED_FIELD,
}


def read_conversation_icon_key(data_source: Any) -> str | None:
    if not isinstance(data_source, dict):
        return None
    return normalize_conversation_icon_key(data_source.get(CONVERSATION_ICON_KEY_FIELD))


def get_or_create_conversation(
    user_id: str,
    conversation_id: str | None,
) -> tuple[str, str, dict[str, Any], str]:
    with Session(engine) as session:
        if conversation_id:
            conv = session.exec(
                select(Conversation).where(Conversation.id == conversation_id)
            ).first()
            if conv is None:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            if conv.user != user_id and not conv.is_public:
                raise HTTPException(status_code=403, detail="Access denied.")
            payload = deepcopy(conv.data_source or {})
            icon_key = read_conversation_icon_key(payload) or DEFAULT_CONVERSATION_ICON_KEY
            if read_conversation_icon_key(payload) is None:
                payload[CONVERSATION_ICON_KEY_FIELD] = icon_key
            return conv.id, normalize_conversation_name(conv.name), payload, icon_key

        conv = Conversation(user=user_id)
        conv.name = normalize_conversation_name("")
        conv.data_source = {
            CONVERSATION_ICON_KEY_FIELD: DEFAULT_CONVERSATION_ICON_KEY,
            CONVERSATION_ICON_REVIEWED_FIELD: False,
        }
        session.add(conv)
        session.commit()
        session.refresh(conv)
        return (
            conv.id,
            normalize_conversation_name(conv.name),
            {
                CONVERSATION_ICON_KEY_FIELD: DEFAULT_CONVERSATION_ICON_KEY,
                CONVERSATION_ICON_REVIEWED_FIELD: False,
            },
            DEFAULT_CONVERSATION_ICON_KEY,
        )


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
        current_payload = deepcopy(conv.data_source or {})
        merged_payload = deepcopy(payload or {})
        for key in PRESERVED_DATA_SOURCE_KEYS:
            if key not in merged_payload and key in current_payload:
                merged_payload[key] = deepcopy(current_payload.get(key))
        conv.data_source = merged_payload
        conv.date_updated = datetime.now(get_localzone())
        session.add(conv)
        session.commit()


def maybe_autoname_conversation(
    *,
    user_id: str,
    conversation_id: str,
    current_name: str,
    message: str,
    agent_mode: str,
) -> tuple[str, str]:
    fallback_icon = infer_conversation_icon_key(message or current_name, agent_mode=agent_mode)
    if not str(message or "").strip():
        return normalize_conversation_name(current_name), fallback_icon

    with Session(engine) as session:
        conv = session.exec(select(Conversation).where(Conversation.id == conversation_id)).first()
        if conv is None:
            generated_name, generated_icon_key = generate_conversation_identity(
                message,
                agent_mode=agent_mode,
            )
            return generated_name, generated_icon_key
        if conv.user != user_id and not conv.is_public:
            current_icon = read_conversation_icon_key(conv.data_source) or fallback_icon
            return normalize_conversation_name(conv.name), current_icon

        current_payload = deepcopy(conv.data_source or {})
        current_icon = read_conversation_icon_key(current_payload)
        icon_reviewed = bool(current_payload.get(CONVERSATION_ICON_REVIEWED_FIELD))
        needs_name = is_placeholder_conversation_name(conv.name)
        needs_icon = (not current_icon) or (
            bool(str(message or "").strip())
            and current_icon == DEFAULT_CONVERSATION_ICON_KEY
            and not icon_reviewed
        )
        changed = False

        if needs_name or needs_icon:
            generated_name, generated_icon_key = generate_conversation_identity(
                message,
                agent_mode=agent_mode,
            )
            if needs_name:
                conv.name = generated_name
                changed = True
            if needs_icon:
                current_payload[CONVERSATION_ICON_KEY_FIELD] = generated_icon_key
                current_payload[CONVERSATION_ICON_REVIEWED_FIELD] = True
                conv.data_source = current_payload
                current_icon = generated_icon_key
                changed = True

        normalized_name = normalize_conversation_name(conv.name)
        if normalized_name != conv.name:
            conv.name = normalized_name
            changed = True

        if changed:
            conv.date_updated = datetime.now(get_localzone())
            session.add(conv)
            session.commit()
            session.refresh(conv)

        icon_key = read_conversation_icon_key(conv.data_source) or current_icon or fallback_icon
        return normalize_conversation_name(conv.name), icon_key
