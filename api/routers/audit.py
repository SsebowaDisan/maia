"""Audit trail HTTP endpoints.

All routes require org_admin or super_admin privileges.
"""
from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.auth import require_org_admin
from api.models.audit_event import AuditEvent
from api.models.user import User
from api.services.audit.trail import (
    count_events,
    export_events_ndjson,
    query_events,
)

router = APIRouter(prefix="/api/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# GET /api/audit/events — filtered list with pagination
# ---------------------------------------------------------------------------

@router.get("/events")
def list_events(
    admin: Annotated[User, Depends(require_org_admin)],
    action: Annotated[str | None, Query()] = None,
    user_id: Annotated[str | None, Query()] = None,
    resource_type: Annotated[str | None, Query()] = None,
    since: Annotated[float | None, Query()] = None,
    until: Annotated[float | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    tenant_id = admin.tenant_id or ""
    events = query_events(
        tenant_id,
        action=action,
        user_id=user_id,
        resource_type=resource_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return [_event_to_dict(e) for e in events]


# ---------------------------------------------------------------------------
# GET /api/audit/events/export — NDJSON stream for SIEM ingestion
# ---------------------------------------------------------------------------

@router.get("/events/export")
def export_events(
    admin: Annotated[User, Depends(require_org_admin)],
    since: Annotated[float | None, Query()] = None,
    until: Annotated[float | None, Query()] = None,
) -> StreamingResponse:
    tenant_id = admin.tenant_id or ""
    return StreamingResponse(
        export_events_ndjson(tenant_id, since=since, until=until),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=audit_export.ndjson"},
    )


# ---------------------------------------------------------------------------
# GET /api/audit/events/stats — action counts for the last 24 h
# ---------------------------------------------------------------------------

_ACTIONS = [
    "auth.login",
    "auth.logout",
    "workflow.run",
    "agent.run",
    "connector.tool_call",
    "admin.role_change",
]


@router.get("/events/stats")
def event_stats(
    admin: Annotated[User, Depends(require_org_admin)],
) -> dict:
    tenant_id = admin.tenant_id or ""
    since_24h = time.time() - 86400
    counts: dict[str, int] = {}
    for action in _ACTIONS:
        counts[action] = count_events(tenant_id, action=action, since=since_24h)
    # Also include a total
    counts["_total"] = count_events(tenant_id, since=since_24h)
    return counts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event_to_dict(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "timestamp": event.timestamp,
        "tenant_id": event.tenant_id,
        "user_id": event.user_id,
        "actor_type": event.actor_type,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "detail": event.detail,
        "ip_address": event.ip_address,
        "metadata_json": event.metadata_json,
    }
