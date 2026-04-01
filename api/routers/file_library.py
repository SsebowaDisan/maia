"""File Library router — flag, review, promote, and dismiss user uploads.

Endpoints
---------
POST /api/file-library/{source_id}/flag       Any user — flag own user_temp file
GET  /api/file-library/flagged                org_admin — list flagged queue
POST /api/file-library/{source_id}/promote    org_admin — move to shared library
POST /api/file-library/{source_id}/dismiss    org_admin — reject flag, restore TTL
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_current_user, require_org_admin
from api.models.user import User
from api.services.upload.file_tier_service import (
    dismiss_source,
    flag_source,
    get_flagged_queue,
    promote_source,
)

router = APIRouter(prefix="/api/file-library", tags=["file-library"])


# ── Request bodies ────────────────────────────────────────────────────────────

class FlagRequest(BaseModel):
    note: str = ""


class DismissRequest(BaseModel):
    reason: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{source_id}/flag")
def flag_file(
    source_id: str,
    body: FlagRequest = FlagRequest(),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Flag a user_temp file for admin review.

    Only the file's owner can flag it. Extends its TTL and notifies all admins.
    """
    try:
        updated = flag_source(
            source_id=source_id,
            requesting_user_id=user.id,
            note=body.note,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "id": updated.id,
        "flagged": updated.flagged,
        "flagged_at": updated.flagged_at,
        "expires_at": updated.expires_at,
        "message": "File submitted for library review.",
    }


@router.get("/flagged")
def list_flagged(
    user: User = Depends(require_org_admin),
) -> list[dict[str, Any]]:
    """Return all files currently flagged for admin review, newest first."""
    return get_flagged_queue()


@router.post("/{source_id}/promote")
def promote_file(
    source_id: str,
    user: User = Depends(require_org_admin),
) -> dict[str, Any]:
    """Promote a flagged file to the shared library.

    Copies the file to LIBRARY_DIR, clears TTL, makes it visible to all users.
    Notifies the original uploader.
    """
    try:
        updated = promote_source(source_id=source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "id": updated.id,
        "scope": updated.scope,
        "upload_url": updated.upload_url,
        "message": f"'{updated.filename}' added to the team library.",
    }


@router.post("/{source_id}/dismiss")
def dismiss_file(
    source_id: str,
    body: DismissRequest = DismissRequest(),
    user: User = Depends(require_org_admin),
) -> dict[str, Any]:
    """Dismiss a flagged file — clears the flag and restores 30-day TTL.

    Optionally sends the uploader a reason.
    """
    try:
        updated = dismiss_source(source_id=source_id, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "id": updated.id,
        "flagged": updated.flagged,
        "expires_at": updated.expires_at,
        "message": "Flag dismissed.",
    }
