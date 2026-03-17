"""Computer Use session registry.

Responsibility:
- lifecycle management for BrowserSession instances,
- per-user session limits,
- per-session stream lease control (no concurrent loops on same session),
- lightweight idempotency for session creation retries.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from .browser_session import BrowserSession

logger = logging.getLogger(__name__)

try:
    from .session_record import close_record, create_record, mark_stale_active_sessions
except Exception:  # pragma: no cover - fallback for minimal test/runtime environments.
    def create_record(*_args, **_kwargs) -> None:
        return None

    def close_record(*_args, **_kwargs) -> None:
        return None

    def mark_stale_active_sessions() -> int:
        return 0


def _read_positive_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return max(1, default)
    try:
        parsed = int(raw)
    except ValueError:
        return max(1, default)
    return max(1, parsed)


_MAX_SESSIONS_PER_USER = _read_positive_int("MAIA_COMPUTER_USE_MAX_SESSIONS_PER_USER", 3)
_MAX_CONCURRENT_STREAMS_PER_USER = _read_positive_int(
    "MAIA_COMPUTER_USE_MAX_CONCURRENT_STREAMS_PER_USER",
    1,
)
_CREATE_IDEMPOTENCY_TTL_SECONDS = 300.0


class SessionLimitExceeded(Exception):
    """Raised when a user exceeds the maximum number of active sessions."""


class StreamLimitExceeded(Exception):
    """Raised when a user exceeds concurrent stream limits."""


@dataclass(frozen=True)
class _CreateIdempotencyEntry:
    session_id: str
    expires_at: float


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._session_owner: dict[str, str] = {}
        self._active_streams: set[str] = set()
        self._active_streams_by_user: dict[str, int] = {}
        self._create_idempotency: dict[tuple[str, str], _CreateIdempotencyEntry] = {}
        self._lock = threading.Lock()
        # Any session that was "active" in the DB before this process started
        # belongs to a dead browser process. Mark those stale immediately.
        try:
            mark_stale_active_sessions()
        except Exception:
            logger.debug("SessionRegistry: could not mark stale sessions", exc_info=True)

    def create(
        self,
        *,
        user_id: str = "",
        start_url: str = "",
        request_id: str | None = None,
    ) -> BrowserSession:
        """Create, start, and register a new BrowserSession.

        If request_id is supplied, creation is idempotent for a short window
        and returns the already-created live session for that user/request_id.
        """
        normalized_user_id = str(user_id or "").strip()
        normalized_request_id = str(request_id or "").strip()

        with self._lock:
            self._prune_idempotency_entries_locked()
            if normalized_request_id:
                existing = self._get_idempotent_session_locked(
                    user_id=normalized_user_id,
                    request_id=normalized_request_id,
                )
                if existing is not None:
                    logger.info(
                        "SessionRegistry: idempotent create replay user=%s request_id=%s session=%s",
                        normalized_user_id,
                        normalized_request_id,
                        existing.session_id,
                    )
                    return existing
            if self._active_session_count_locked(normalized_user_id) >= _MAX_SESSIONS_PER_USER:
                raise SessionLimitExceeded(
                    f"Maximum active computer sessions reached ({_MAX_SESSIONS_PER_USER})."
                )

        session_id = str(uuid.uuid4())
        session = BrowserSession(session_id=session_id)
        session.start()

        with self._lock:
            self._sessions[session_id] = session
            self._session_owner[session_id] = normalized_user_id
            if normalized_request_id:
                self._create_idempotency[(normalized_user_id, normalized_request_id)] = (
                    _CreateIdempotencyEntry(
                        session_id=session_id,
                        expires_at=time.time() + _CREATE_IDEMPOTENCY_TTL_SECONDS,
                    )
                )
        try:
            create_record(session_id, user_id=normalized_user_id, start_url=start_url)
        except Exception:
            logger.debug("SessionRegistry: could not persist session record", exc_info=True)
        logger.info("SessionRegistry: created %s user=%s", session_id, normalized_user_id)
        return session

    def get(self, session_id: str) -> Optional[BrowserSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def get_for_user(self, session_id: str, *, user_id: str) -> Optional[BrowserSession]:
        normalized_user_id = str(user_id or "").strip()
        with self._lock:
            if self._session_owner.get(session_id) != normalized_user_id:
                return None
            return self._sessions.get(session_id)

    def close(self, session_id: str) -> bool:
        """Close and deregister the session. Returns True if it existed."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
            owner = self._session_owner.pop(session_id, "")
            was_streaming = session_id in self._active_streams
            if was_streaming:
                self._active_streams.discard(session_id)
                if owner:
                    current = int(self._active_streams_by_user.get(owner, 0))
                    if current <= 1:
                        self._active_streams_by_user.pop(owner, None)
                    else:
                        self._active_streams_by_user[owner] = current - 1
        if session is None:
            return False
        session.close()
        try:
            close_record(session_id)
        except Exception:
            logger.debug("SessionRegistry: could not close session record", exc_info=True)
        logger.info("SessionRegistry: closed %s", session_id)
        return True

    def close_all(self) -> None:
        with self._lock:
            ids = list(self._sessions.keys())
        for sid in ids:
            self.close(sid)

    def active_session_ids(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())

    def try_acquire_stream_lease(self, *, session_id: str, user_id: str) -> None:
        """Reserve stream execution for a session/user.

        Raises StreamLimitExceeded when user has too many active streams.
        Raises KeyError when session is unknown.
        Raises RuntimeError when session already has an active stream.
        """
        normalized_user_id = str(user_id or "").strip()
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(session_id)
            owner = self._session_owner.get(session_id, "")
            if owner != normalized_user_id:
                raise KeyError(session_id)
            if session_id in self._active_streams:
                raise RuntimeError("Session already has an active stream.")
            current_user_streams = int(self._active_streams_by_user.get(normalized_user_id, 0))
            if current_user_streams >= _MAX_CONCURRENT_STREAMS_PER_USER:
                raise StreamLimitExceeded(
                    "Maximum concurrent Computer Use streams reached "
                    f"({_MAX_CONCURRENT_STREAMS_PER_USER})."
                )
            self._active_streams.add(session_id)
            self._active_streams_by_user[normalized_user_id] = current_user_streams + 1

    def release_stream_lease(self, *, session_id: str, user_id: str) -> None:
        normalized_user_id = str(user_id or "").strip()
        with self._lock:
            if session_id not in self._active_streams:
                return
            self._active_streams.discard(session_id)
            current = int(self._active_streams_by_user.get(normalized_user_id, 0))
            if current <= 1:
                self._active_streams_by_user.pop(normalized_user_id, None)
            else:
                self._active_streams_by_user[normalized_user_id] = current - 1

    def _active_session_count_locked(self, user_id: str) -> int:
        if not user_id:
            return len(self._sessions)
        return sum(1 for sid in self._sessions if self._session_owner.get(sid, "") == user_id)

    def _prune_idempotency_entries_locked(self) -> None:
        now = time.time()
        stale_keys = [
            key
            for key, entry in self._create_idempotency.items()
            if entry.expires_at <= now or entry.session_id not in self._sessions
        ]
        for key in stale_keys:
            self._create_idempotency.pop(key, None)

    def _get_idempotent_session_locked(self, *, user_id: str, request_id: str) -> BrowserSession | None:
        entry = self._create_idempotency.get((user_id, request_id))
        if entry is None:
            return None
        if entry.expires_at <= time.time():
            self._create_idempotency.pop((user_id, request_id), None)
            return None
        return self._sessions.get(entry.session_id)


_registry: Optional[SessionRegistry] = None
_registry_lock = threading.Lock()


def get_session_registry() -> SessionRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = SessionRegistry()
    return _registry
