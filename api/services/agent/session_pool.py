"""Warm agent session pool.

Keeps a small in-process pool of warm agent sessions keyed by
``user_id:conversation_id``.  Each session caches the resolved LLM config
so subsequent turns in the same conversation skip the cold-construction
overhead.

Usage
-----
    session = SessionPool.acquire(user_id, conversation_id)
    try:
        # use session.llm_config ...
    finally:
        SessionPool.release(user_id, conversation_id)

    # When a conversation ends:
    SessionPool.evict(user_id, conversation_id)

Configuration (env vars)
------------------------
    MAIA_AGENT_SESSION_IDLE_SECONDS   — idle timeout before eviction (default 300)
    MAIA_AGENT_SESSION_POOL_SIZE      — max live sessions (default 50, LRU eviction)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_IDLE_SECONDS = int(os.environ.get("MAIA_AGENT_SESSION_IDLE_SECONDS", "300"))
_MAX_POOL_SIZE = int(os.environ.get("MAIA_AGENT_SESSION_POOL_SIZE", "50"))
_EVICTION_INTERVAL_SECONDS = 60


@dataclass
class AgentSession:
    """Cached per-conversation state for an agent session."""
    user_id: str
    conversation_id: str
    # Resolved LLM config — None until first acquisition populates it.
    llm_config: dict[str, Any] = field(default_factory=dict)
    last_used: float = field(default_factory=time.monotonic)
    # Hook for any additional warm-state callers want to store.
    extra: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_used = time.monotonic()

    def is_idle(self, idle_seconds: int = _IDLE_SECONDS) -> bool:
        return (time.monotonic() - self.last_used) > idle_seconds


class _SessionPool:
    """Thread-safe LRU pool of ``AgentSession`` objects."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Ordered dict preserves insertion order → easy LRU eviction at cap.
        self._sessions: dict[str, AgentSession] = {}
        self._eviction_thread = threading.Thread(
            target=self._eviction_loop, daemon=True, name="session-pool-evictor"
        )
        self._eviction_thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(self, user_id: str, conversation_id: str) -> AgentSession:
        """Return an existing warm session or create a fresh one.

        Resets the idle timer and moves the session to MRU position.
        Never raises — if creation fails it returns a blank session so
        callers can still proceed with cold construction.
        """
        key = self._key(user_id, conversation_id)
        with self._lock:
            session = self._sessions.get(key)
            if session is not None:
                session.touch()
                # Move to end (MRU position).
                self._sessions.pop(key)
                self._sessions[key] = session
                logger.debug("session_pool.hit key=%s", key)
                return session
            # Cap enforcement — evict LRU entry if full.
            if len(self._sessions) >= _MAX_POOL_SIZE:
                lru_key = next(iter(self._sessions))
                del self._sessions[lru_key]
                logger.debug("session_pool.lru_evict key=%s", lru_key)
            session = AgentSession(user_id=user_id, conversation_id=conversation_id)
            self._sessions[key] = session
            logger.debug("session_pool.miss key=%s pool_size=%d", key, len(self._sessions))
            return session

    def release(self, user_id: str, conversation_id: str) -> None:
        """Mark the session as available (resets idle timer without evicting)."""
        key = self._key(user_id, conversation_id)
        with self._lock:
            session = self._sessions.get(key)
            if session is not None:
                session.touch()

    def evict(self, user_id: str, conversation_id: str) -> None:
        """Remove a session from the pool (call on conversation delete / logout)."""
        key = self._key(user_id, conversation_id)
        with self._lock:
            removed = self._sessions.pop(key, None)
            if removed is not None:
                logger.debug("session_pool.evict key=%s", key)

    def pool_size(self) -> int:
        with self._lock:
            return len(self._sessions)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _key(user_id: str, conversation_id: str) -> str:
        return f"{user_id}:{conversation_id}"

    def _eviction_loop(self) -> None:
        """Background thread: evict idle sessions every 60 seconds."""
        while True:
            time.sleep(_EVICTION_INTERVAL_SECONDS)
            self._evict_idle()

    def _evict_idle(self) -> None:
        with self._lock:
            idle_keys = [
                k for k, s in self._sessions.items() if s.is_idle()
            ]
        for key in idle_keys:
            with self._lock:
                session = self._sessions.get(key)
                if session is not None and session.is_idle():
                    del self._sessions[key]
                    logger.debug("session_pool.idle_evict key=%s", key)


# Module-level singleton — import and use directly.
SessionPool = _SessionPool()
