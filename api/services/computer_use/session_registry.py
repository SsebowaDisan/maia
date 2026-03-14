"""B1-CU-04 — Computer Use session registry.

Responsibility: in-memory lifecycle management for BrowserSession instances.
Thread-safe via a lock; sessions are keyed by UUID session_id.
"""
from __future__ import annotations

import threading
import uuid
import logging
from typing import Optional

from .browser_session import BrowserSession

logger = logging.getLogger(__name__)


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = threading.Lock()

    def create(self) -> BrowserSession:
        """Create, start, and register a new BrowserSession."""
        session_id = str(uuid.uuid4())
        session = BrowserSession(session_id=session_id)
        session.start()
        with self._lock:
            self._sessions[session_id] = session
        logger.info("SessionRegistry: created %s", session_id)
        return session

    def get(self, session_id: str) -> Optional[BrowserSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def close(self, session_id: str) -> bool:
        """Close and deregister the session.  Returns True if it existed."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session.close()
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


_registry: Optional[SessionRegistry] = None
_registry_lock = threading.Lock()


def get_session_registry() -> SessionRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = SessionRegistry()
    return _registry
