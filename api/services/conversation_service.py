from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import uuid

from fastapi import HTTPException
from sqlmodel import Session, select
from tzlocal import get_localzone

from ktem.db.models import Conversation, MindmapShare, engine
from api.services.chat.conversation_naming import (
    extract_conversation_icon,
    generate_conversation_name,
    is_legacy_fallback_icon,
    is_placeholder_conversation_name,
    normalize_conversation_name,
    strip_icon_prefix,
)

AUTONAME_BACKFILL_LIMIT = 8
ICON_REFRESH_BACKFILL_LIMIT = 8


def _normalize_mindmap_payload(raw_payload: dict | None) -> dict:
    if not isinstance(raw_payload, dict):
        return {}
    payload = deepcopy(raw_payload)
    if not isinstance(payload.get("nodes"), list):
        payload["nodes"] = []
    if not isinstance(payload.get("edges"), list):
        payload["edges"] = []
    if not isinstance(payload.get("title"), str):
        payload["title"] = "Mind-map"
    return payload


def _ensure_owner(user_id: str, conv: Conversation) -> None:
    if conv.user != user_id:
        raise HTTPException(status_code=403, detail="Only owner can update.")


def _first_user_message(data_source: dict) -> str:
    if not isinstance(data_source, dict):
        return ""
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
    if not isinstance(data_source, dict):
        return "ask"
    state = data_source.get("state")
    if isinstance(state, dict):
        mode = str(state.get("mode") or "").strip()
        if mode:
            return mode
    return "ask"


def _to_summary(conv: Conversation) -> dict:
    data_source = conv.data_source if isinstance(conv.data_source, dict) else {}
    messages_raw = data_source.get("messages", [])
    message_count = len(messages_raw) if isinstance(messages_raw, list) else 0
    return {
        "id": conv.id,
        "name": normalize_conversation_name(conv.name),
        "user": conv.user,
        "is_public": conv.is_public,
        "date_created": conv.date_created,
        "date_updated": conv.date_updated,
        "message_count": message_count,
    }


def list_conversations(user_id: str) -> list[dict]:
    with Session(engine) as session:
        def _load_rows() -> list[Conversation]:
            return session.exec(
                select(Conversation)
                .where(Conversation.user == user_id)
                .order_by(Conversation.date_updated.desc())  # type: ignore[attr-defined]
            ).all()

        rows = _load_rows()

        backfilled = 0
        icon_refreshed = 0
        for row in rows:
            if backfilled >= AUTONAME_BACKFILL_LIMIT and icon_refreshed >= ICON_REFRESH_BACKFILL_LIMIT:
                break
            data_source = row.data_source if isinstance(row.data_source, dict) else {}
            first_message = _first_user_message(data_source)
            agent_mode = _agent_mode_from_state(data_source)
            updated = False

            if backfilled < AUTONAME_BACKFILL_LIMIT and is_placeholder_conversation_name(row.name) and first_message:
                try:
                    row.name = generate_conversation_name(
                        first_message,
                        agent_mode=agent_mode,
                    )
                except Exception:
                    # Conversation listing must stay reliable even if LLM naming fails.
                    row.name = normalize_conversation_name(first_message)
                backfilled += 1
                updated = True

            current_icon = extract_conversation_icon(row.name)
            if (
                icon_refreshed < ICON_REFRESH_BACKFILL_LIMIT
                and is_legacy_fallback_icon(current_icon)
                and first_message
            ):
                suggested_icon = None
                try:
                    regenerated = generate_conversation_name(first_message, agent_mode=agent_mode)
                    suggested_icon = extract_conversation_icon(regenerated)
                except Exception:
                    suggested_icon = None

                refreshed_name = normalize_conversation_name(
                    strip_icon_prefix(row.name),
                    icon=suggested_icon,
                )
                if refreshed_name != row.name:
                    row.name = refreshed_name
                    icon_refreshed += 1
                    updated = True

            if updated:
                row.date_updated = datetime.now(get_localzone())
                session.add(row)

        if backfilled or icon_refreshed:
            session.commit()
            # Commit expires ORM state; reload rows before converting to summaries.
            rows = _load_rows()

        # Build summaries while the session is still active to avoid detached-instance
        # refresh issues on deferred/expired attributes.
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


def create_mindmap_share(
    user_id: str,
    conversation_id: str,
    mindmap: dict | None,
    title: str | None = None,
) -> dict:
    with Session(engine) as session:
        conv = session.exec(
            select(Conversation).where(Conversation.id == conversation_id)
        ).first()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        _ensure_owner(user_id, conv)

        payload = _normalize_mindmap_payload(mindmap)
        if not payload:
            raise HTTPException(status_code=400, detail="Mind-map payload is empty.")

        map_title = " ".join(str(title or payload.get("title", "")).split()).strip()
        if not map_title:
            map_title = "Mind-map"

        now = datetime.now(get_localzone())
        share = MindmapShare(
            share_id=uuid.uuid4().hex[:16],
            conversation_id=conversation_id,
            user=user_id,
            title=map_title[:160],
            payload=payload,
            date_created=now,
            date_updated=now,
        )
        session.add(share)
        session.commit()
        session.refresh(share)

    return {
        "share_id": share.share_id,
        "conversation_id": share.conversation_id,
        "title": share.title,
        "date_created": share.date_created,
        "map": deepcopy(share.payload or {}),
    }


def get_mindmap_share(share_id: str) -> dict:
    share_id_norm = " ".join(str(share_id or "").split()).strip()
    if not share_id_norm:
        raise HTTPException(status_code=404, detail="Mind-map share not found.")

    with Session(engine) as session:
        share = session.exec(
            select(MindmapShare).where(MindmapShare.share_id == share_id_norm)
        ).first()
        if share is None:
            raise HTTPException(status_code=404, detail="Mind-map share not found.")
        return {
            "share_id": share.share_id,
            "conversation_id": share.conversation_id,
            "title": share.title,
            "date_created": share.date_created,
            "map": deepcopy(share.payload or {}),
        }
