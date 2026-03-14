"""B4-06 — Bidirectional webhook management.

Responsibility: register/deregister webhooks with external services and
store the mapping so the event trigger engine can route incoming events.

Webhook receiver URL: /api/webhooks/{tenant_id}/{connector_id}
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)

# How to call the external API to create/delete webhooks — per connector
_WEBHOOK_APIS: dict[str, dict[str, str]] = {
    "slack": {
        "create": "https://slack.com/api/apps.event.authorizations.list",  # stub
        "delete": "https://slack.com/api/apps.event.authorizations.list",
    },
    "github": {
        "create": "https://api.github.com/repos/{repo}/hooks",
        "delete": "https://api.github.com/repos/{repo}/hooks/{hook_id}",
    },
}


class WebhookRegistration(SQLModel, table=True):
    __tablename__ = "maia_webhook_registration"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    connector_id: str = Field(index=True)
    event_types_json: str = "[]"
    external_hook_id: Optional[str] = None  # ID returned by the external service
    receiver_url: str = ""
    active: bool = True
    created_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def register_webhook(
    tenant_id: str,
    connector_id: str,
    event_types: list[str],
    *,
    base_url: str = "",
    extra_params: dict[str, Any] | None = None,
) -> WebhookRegistration:
    """Register a webhook with the external connector and persist the record."""
    _ensure_tables()
    receiver_url = f"{base_url.rstrip('/')}/api/webhooks/{tenant_id}/{connector_id}"

    external_id = _call_external_create(
        connector_id=connector_id,
        tenant_id=tenant_id,
        event_types=event_types,
        receiver_url=receiver_url,
        extra_params=extra_params or {},
    )

    record = WebhookRegistration(
        tenant_id=tenant_id,
        connector_id=connector_id,
        event_types_json=json.dumps(event_types),
        external_hook_id=external_id,
        receiver_url=receiver_url,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)

    # Auto-subscribe matched agents
    _auto_subscribe_agents(tenant_id, connector_id, event_types)

    logger.info(
        "Webhook registered: tenant=%s connector=%s events=%s",
        tenant_id,
        connector_id,
        event_types,
    )
    return record


def list_webhooks(tenant_id: str) -> Sequence[WebhookRegistration]:
    with Session(engine) as session:
        return session.exec(
            select(WebhookRegistration)
            .where(WebhookRegistration.tenant_id == tenant_id)
            .where(WebhookRegistration.active == True)  # noqa: E712
        ).all()


def deregister_webhook(tenant_id: str, webhook_id: str) -> bool:
    with Session(engine) as session:
        record = session.exec(
            select(WebhookRegistration)
            .where(WebhookRegistration.id == webhook_id)
            .where(WebhookRegistration.tenant_id == tenant_id)
        ).first()
        if not record:
            return False

        _call_external_delete(record.connector_id, record.external_hook_id)

        record.active = False
        session.add(record)
        session.commit()
    return True


# ── Private ────────────────────────────────────────────────────────────────────

def _call_external_create(
    *,
    connector_id: str,
    tenant_id: str,
    event_types: list[str],
    receiver_url: str,
    extra_params: dict[str, Any],
) -> Optional[str]:
    """Attempt to register a webhook with the external service.  Returns hook ID or None."""
    try:
        from api.services.connectors.vault import get_credential

        credentials = get_credential(tenant_id, connector_id) or {}
        api_info = _WEBHOOK_APIS.get(connector_id)
        if not api_info:
            logger.debug("No webhook API config for connector %s — skipping external call", connector_id)
            return None

        url_template = api_info.get("create", "")
        url = url_template.format(**extra_params)
        token = credentials.get("access_token") or credentials.get("api_key") or ""
        payload = {
            "url": receiver_url,
            "events": event_types,
            **extra_params,
        }
        import urllib.request

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return str(data.get("id") or data.get("hook_id") or "")
    except Exception as exc:
        logger.debug("External webhook create call failed: %s", exc)
        return None


def _call_external_delete(connector_id: str, hook_id: Optional[str]) -> None:
    if not hook_id:
        return
    try:
        api_info = _WEBHOOK_APIS.get(connector_id)
        if not api_info:
            return
        url = api_info.get("delete", "").format(hook_id=hook_id)
        import urllib.request

        req = urllib.request.Request(url, method="DELETE")
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _auto_subscribe_agents(tenant_id: str, connector_id: str, event_types: list[str]) -> None:
    """Subscribe any agents that have a matching on_event trigger."""
    try:
        from api.services.agents.event_triggers import subscribe_agent_to_event
        from api.services.agents.definition_store import list_agents, load_schema

        for record in list_agents(tenant_id):
            schema = load_schema(record)
            trigger = getattr(schema, "trigger", None)
            if not trigger or getattr(trigger, "family", None) != "on_event":
                continue
            event_pattern = getattr(trigger, "event_type", None)
            if not event_pattern:
                continue
            for et in event_types:
                full = f"{connector_id}.{et}"
                import fnmatch

                if fnmatch.fnmatch(full, event_pattern):
                    subscribe_agent_to_event(tenant_id, record.agent_id, event_pattern, connector_id)
                    break
    except Exception:
        logger.debug("Auto-subscription failed", exc_info=True)
