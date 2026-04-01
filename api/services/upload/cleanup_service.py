"""User-temp file cleanup service.

Runs a background thread that wakes up once every 24 hours and deletes
user_temp files whose expires_at timestamp has passed AND that are not
currently flagged (flagged files keep their extended TTL until an admin acts).

Nothing is deleted from the vector store or doc store — those entries are
small and harmless to keep. Only the original file bytes on disk are removed,
and the source is removed from the registry so it no longer appears in listings.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 86400  # 24 hours


class UserTempCleanupService:
    def __init__(self) -> None:
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._loop,
            daemon=True,
            name="maia-user-temp-cleanup",
        )
        self._thread.start()
        logger.info("UserTempCleanupService started (interval=%ds)", _CHECK_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        # Run once at startup (catches anything that expired while server was down)
        self.run_once()
        while not self._stop_event.wait(timeout=_CHECK_INTERVAL_SECONDS):
            self.run_once()

    def run_once(self) -> None:
        """Single cleanup pass — safe to call manually (e.g. in tests)."""
        try:
            deleted_files, deleted_records = _do_cleanup()
            if deleted_files or deleted_records:
                logger.info(
                    "UserTemp cleanup: deleted %d files, %d registry entries",
                    deleted_files,
                    deleted_records,
                )
        except Exception as exc:
            logger.warning("UserTemp cleanup pass failed: %s", exc)


def _do_cleanup() -> tuple[int, int]:
    """Delete expired, non-flagged user_temp sources. Returns (files_deleted, records_deleted)."""
    from api.services.rag.bridge import (
        list_registered_sources,
        remove_registered_source,
    )

    now = datetime.now(timezone.utc)
    files_deleted = 0
    records_deleted = 0

    # include_chat_temp=True so we see user_temp entries
    all_sources = list_registered_sources(include_chat_temp=True)

    for source in all_sources:
        if source.scope not in {"user_temp", "chat_temp"}:
            continue
        if source.flagged:
            continue  # flagged files wait for admin action
        if not source.expires_at:
            continue  # no TTL set — skip

        try:
            expiry = datetime.fromisoformat(source.expires_at)
            # Make timezone-aware if naive
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        if expiry > now:
            continue  # not expired yet

        # Delete file from disk
        raw_path = str(source.upload_url or "").strip()
        if raw_path and not raw_path.startswith(("http://", "https://")):
            path = Path(raw_path)
            if path.exists():
                try:
                    path.unlink()
                    files_deleted += 1
                except Exception as exc:
                    logger.warning("Could not delete file %s: %s", path, exc)

        # Remove from registry
        remove_registered_source(source.id)
        records_deleted += 1

    return files_deleted, records_deleted


# ── Singleton ─────────────────────────────────────────────────────────────────

_cleanup_service: UserTempCleanupService | None = None


def get_cleanup_service() -> UserTempCleanupService:
    global _cleanup_service
    if _cleanup_service is None:
        _cleanup_service = UserTempCleanupService()
    return _cleanup_service
