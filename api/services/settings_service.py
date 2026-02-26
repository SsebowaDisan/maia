from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from sqlmodel import Session, select

from ktem.db.models import Settings, engine

from api.context import ApiContext


def _allowed_keys(context: ApiContext) -> set[str]:
    base = set(context.default_settings.keys())
    # Agent settings are API-owned controls and are intentionally allowed
    # even if they are not part of KTEM default settings.
    base.update(
        {
            "agent.user_role",
            "agent.access_mode",
            "agent.full_access_enabled",
            "agent.tenant_id",
            "agent.mode_default",
            "agent.docs_provider",
            "agent.smtp_host",
            "agent.smtp_port",
            "agent.smtp_username",
            "agent.smtp_password",
            "agent.ollama.base_url",
            "agent.ollama.default_model",
            "agent.ollama.embedding_model",
        }
    )
    return base


def load_user_settings(context: ApiContext, user_id: str) -> dict[str, Any]:
    values = deepcopy(context.default_settings)
    with Session(engine) as session:
        setting_row = session.exec(select(Settings).where(Settings.user == user_id)).first()
        if setting_row and setting_row.setting:
            values.update(setting_row.setting)
    values.setdefault("agent.user_role", "member")
    values.setdefault("agent.access_mode", "restricted")
    values.setdefault("agent.full_access_enabled", False)
    values.setdefault("agent.tenant_id", user_id)
    values.setdefault("agent.mode_default", "ask")
    values.setdefault("agent.docs_provider", "local")
    values.setdefault("agent.smtp_host", "")
    values.setdefault("agent.smtp_port", 587)
    values.setdefault("agent.smtp_username", "")
    values.setdefault("agent.smtp_password", "")
    values.setdefault(
        "agent.ollama.base_url",
        str(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).strip()
        or "http://127.0.0.1:11434",
    )
    values.setdefault("agent.ollama.default_model", "")
    values.setdefault("agent.ollama.embedding_model", "")
    return values


def save_user_settings(
    context: ApiContext,
    user_id: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    allowed = _allowed_keys(context)
    sanitized = {key: value for key, value in values.items() if key in allowed}

    with Session(engine) as session:
        setting_row = session.exec(select(Settings).where(Settings.user == user_id)).first()
        if setting_row is None:
            setting_row = Settings(user=user_id)
        setting_row.setting = sanitized
        session.add(setting_row)
        session.commit()

    return sanitized
