"""File-tier service — flag, promote, dismiss, and list flagged sources.

Business rules:
- Any authenticated user can flag their own user_temp file.
- Only org_admin / super_admin can see the flagged queue, promote, or dismiss.
- Promoting copies the file to LIBRARY_DIR and changes scope to "library".
- Dismissing clears the flag and restores the original 30-day TTL.
- Library files are shared (visible to all users regardless of owner).
"""
from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from api.services.rag.bridge import (
    get_registered_source,
    list_flagged_sources,
    remove_registered_source,
    update_registered_source,
)
from api.services.rag.types import SourceRecord
from api.services.upload.storage_config import (
    FLAGGED_TTL_DAYS,
    LIBRARY_DIR,
    USER_TEMP_TTL_DAYS,
    ensure_dirs,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ttl_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


# ── Flag ─────────────────────────────────────────────────────────────────────

def flag_source(
    source_id: str,
    requesting_user_id: str,
    note: str = "",
) -> SourceRecord:
    """Flag a user_temp source for admin review.

    Raises ValueError if not found, not owned by the user, or already library.
    """
    source = get_registered_source(source_id)
    if source is None:
        raise ValueError(f"Source '{source_id}' not found.")
    if source.owner_id and source.owner_id != requesting_user_id:
        raise PermissionError("You can only flag your own files.")
    if source.scope == "library":
        raise ValueError("This file is already in the library.")

    updated = replace(
        source,
        flagged=True,
        flagged_at=_now_iso(),
        flag_note=(note or "").strip(),
        # Reset TTL from today so flagged files get a fresh 30 days
        expires_at=_ttl_iso(FLAGGED_TTL_DAYS),
        updated_at=_now_iso(),
    )
    update_registered_source(updated)

    # Notify all admins in platform
    _notify_admins_file_flagged(updated)

    return updated


# ── Flagged queue (admin) ─────────────────────────────────────────────────────

def get_flagged_queue() -> list[dict[str, Any]]:
    """Return serialized list of all flagged sources for admin review."""
    sources = list_flagged_sources()
    return [_serialize(s) for s in sources]


# ── Promote (admin) ───────────────────────────────────────────────────────────

def promote_source(source_id: str) -> SourceRecord:
    """Promote a flagged user_temp file to the shared library.

    Copies the file to LIBRARY_DIR, sets scope="library", clears TTL and flag.
    Notifies the original uploader.
    """
    ensure_dirs()
    source = get_registered_source(source_id)
    if source is None:
        raise ValueError(f"Source '{source_id}' not found.")

    # Resolve the file on disk
    src_path = _resolve_path(source)
    if src_path is None or not src_path.exists():
        raise FileNotFoundError(
            f"File for source '{source_id}' not found on disk at '{source.upload_url}'."
        )

    # Copy to library dir (flat, prefixed with source_id to avoid collisions)
    dest_path = LIBRARY_DIR / f"{source_id}_{src_path.name}"
    shutil.copy2(src_path, dest_path)

    updated = replace(
        source,
        scope="library",
        flagged=False,
        flagged_at=None,
        flag_note="",
        expires_at=None,        # library files never expire
        upload_url=str(dest_path),
        updated_at=_now_iso(),
    )
    update_registered_source(updated)

    _notify_user_promoted(updated)
    logger.info("Source promoted to library: id=%s filename=%s", source_id, source.filename)
    return updated


# ── Dismiss (admin) ───────────────────────────────────────────────────────────

def dismiss_source(source_id: str, reason: str = "") -> SourceRecord:
    """Dismiss a flagged file — clears flag, restores normal 30-day TTL.

    Optionally notifies the original uploader with a reason.
    """
    source = get_registered_source(source_id)
    if source is None:
        raise ValueError(f"Source '{source_id}' not found.")

    updated = replace(
        source,
        flagged=False,
        flagged_at=None,
        flag_note="",
        # Give the user another 30 days from now after dismissal
        expires_at=_ttl_iso(USER_TEMP_TTL_DAYS),
        updated_at=_now_iso(),
    )
    update_registered_source(updated)

    _notify_user_dismissed(updated, reason)
    logger.info("Flag dismissed: id=%s filename=%s", source_id, source.filename)
    return updated


# ── Serialization ─────────────────────────────────────────────────────────────

def _serialize(source: SourceRecord) -> dict[str, Any]:
    return {
        "id": source.id,
        "filename": source.filename,
        "source_type": source.source_type.value if hasattr(source.source_type, "value") else str(source.source_type),
        "file_size": source.file_size,
        "owner_id": source.owner_id,
        "scope": source.scope,
        "flagged": source.flagged,
        "flagged_at": source.flagged_at,
        "expires_at": source.expires_at,
        "flag_note": source.flag_note,
        "rag_ready": source.rag_ready,
        "citation_ready": source.citation_ready,
        "created_at": source.created_at,
        "upload_url": source.upload_url,
    }


# ── Notifications ─────────────────────────────────────────────────────────────

def _notify_admins_file_flagged(source: SourceRecord) -> None:
    try:
        from api.services.auth.store import list_all_active_users
        from api.services.marketplace.notifications import notify as _notify

        admins = [
            u for u in list_all_active_users()
            if str(u.role or "").strip().lower() in {"org_admin", "super_admin"}
        ]
        for admin in admins:
            try:
                _notify(
                    user_id=admin.id,
                    agent_id=source.id,
                    agent_name=source.filename,
                    event_type="file_flagged",
                    detail=source.flag_note or "",
                )
            except Exception:
                pass
    except Exception as exc:
        logger.warning("Failed to notify admins of flagged file: %s", exc)


def _notify_user_promoted(source: SourceRecord) -> None:
    if not source.owner_id:
        return
    try:
        from api.services.marketplace.notifications import notify as _notify
        _notify(
            user_id=source.owner_id,
            agent_id=source.id,
            agent_name=source.filename,
            event_type="file_promoted",
            detail="",
        )
    except Exception as exc:
        logger.warning("Failed to notify user of promoted file: %s", exc)


def _notify_user_dismissed(source: SourceRecord, reason: str) -> None:
    if not source.owner_id:
        return
    try:
        from api.services.marketplace.notifications import notify as _notify
        _notify(
            user_id=source.owner_id,
            agent_id=source.id,
            agent_name=source.filename,
            event_type="file_dismissed",
            detail=reason or "",
        )
    except Exception as exc:
        logger.warning("Failed to notify user of dismissed file: %s", exc)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _resolve_path(source: SourceRecord) -> Path | None:
    raw = str(source.upload_url or "").strip()
    if not raw or raw.startswith(("http://", "https://")):
        return None
    return Path(raw)
