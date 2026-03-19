"""Webhook Triggers API - configure event-driven agent triggers.

Endpoints:
    GET  /api/triggers               - list all triggers for the user
    POST /api/triggers               - create a webhook trigger
    DELETE /api/triggers/:trigger_id - remove a trigger
    POST /api/triggers/test          - send a test event to trigger matching
    GET  /api/triggers/events        - list available event types
"""
from __future__ import annotations

import fnmatch
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from api.auth import get_current_user_id
from api.services.agents.event_triggers import (
    EventSubscription,
    list_subscriptions,
    subscribe_agent_to_event,
)
from ktem.db.engine import engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/triggers", tags=["triggers"])


class CreateTriggerRequest(BaseModel):
    agent_id: str
    event_type: str = Field(max_length=120)
    source_connector_id: str = Field(default="", max_length=80)
    filter_expression: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=300)


class TestTriggerRequest(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


AVAILABLE_EVENT_TYPES = [
    {
        "event_type": "connector.*.created",
        "label": "New record created",
        "description": "Fires when a new record is created in any connector.",
    },
    {
        "event_type": "connector.*.updated",
        "label": "Record updated",
        "description": "Fires when an existing record is modified.",
    },
    {
        "event_type": "slack.message_received",
        "label": "Slack message",
        "description": "Fires when a message is posted in a monitored Slack channel.",
    },
    {
        "event_type": "email.received",
        "label": "Email received",
        "description": "Fires when a new email arrives in the connected inbox.",
    },
    {
        "event_type": "page_changed",
        "label": "Web page changed",
        "description": "Fires when monitored web page content changes.",
    },
    {
        "event_type": "schedule.cron",
        "label": "Scheduled time",
        "description": "Fires on a cron schedule.",
    },
    {
        "event_type": "webhook.inbound",
        "label": "Inbound webhook",
        "description": "Fires when an external service sends a webhook.",
    },
    {
        "event_type": "workflow.completed",
        "label": "Workflow completed",
        "description": "Fires when another workflow finishes.",
    },
    {
        "event_type": "workflow.failed",
        "label": "Workflow failed",
        "description": "Fires when a workflow fails.",
    },
]


@router.get("")
def list_triggers(user_id: str = Depends(get_current_user_id)) -> list[dict[str, Any]]:
    """List all event triggers for the current user."""
    try:
        rows = list_subscriptions(tenant_id=user_id)
        return [
            {
                "trigger_id": str(row.id),
                "agent_id": row.agent_id,
                "event_type": row.event_pattern,
                "source_connector_id": row.connector_id,
                "enabled": bool(row.enabled),
            }
            for row in rows
        ]
    except Exception:
        return []


@router.post("", status_code=status.HTTP_201_CREATED)
def create_trigger(
    body: CreateTriggerRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Create a new event trigger for an agent."""
    try:
        result = subscribe_agent_to_event(
            tenant_id=user_id,
            agent_id=body.agent_id,
            event_pattern=body.event_type,
            connector_id=body.source_connector_id or "webhook",
        )
        return {
            "trigger_id": str(result.id),
            "agent_id": result.agent_id,
            "event_type": result.event_pattern,
            "source_connector_id": result.connector_id,
            "enabled": bool(result.enabled),
            "description": body.description,
            "filter_expression": body.filter_expression,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{trigger_id}")
def delete_trigger(
    trigger_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Remove an event trigger."""
    try:
        trigger_pk = int(trigger_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid trigger id.") from exc

    try:
        with Session(engine) as session:
            row = session.exec(
                select(EventSubscription)
                .where(EventSubscription.tenant_id == user_id)
                .where(EventSubscription.id == trigger_pk)
                .where(EventSubscription.enabled == True)  # noqa: E712
            ).first()
            if not row:
                raise HTTPException(status_code=404, detail="Trigger not found.")
            row.enabled = False
            session.add(row)
            session.commit()
        return {"status": "deleted", "trigger_id": trigger_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/test")
def test_trigger(
    body: TestTriggerRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Send a test event and return matching subscriptions."""
    try:
        subs = list_subscriptions(tenant_id=user_id)
        matched = [
            row
            for row in subs
            if bool(row.enabled) and fnmatch.fnmatch(body.event_type, row.event_pattern)
        ]
        matched_agents = sorted({row.agent_id for row in matched})
        return {
            "event_type": body.event_type,
            "matched_agents": matched_agents,
            "count": len(matched_agents),
            "matched_triggers": [
                {
                    "trigger_id": str(row.id),
                    "agent_id": row.agent_id,
                    "event_type": row.event_pattern,
                    "source_connector_id": row.connector_id,
                }
                for row in matched
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/events")
def list_event_types() -> list[dict[str, Any]]:
    """List available event types that can trigger agents."""
    return AVAILABLE_EVENT_TYPES
