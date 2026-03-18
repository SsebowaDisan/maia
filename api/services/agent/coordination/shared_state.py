"""Shared state bus for inter-agent communication within a single run.

Provides a publish/subscribe mechanism so agents working on the same run can
share facts, findings, and intermediate results without direct coupling.

Thread-safe: uses threading.Lock for mutations and threading.Event for
blocking wait_for() semantics.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class SharedStateBus:
    """In-memory shared state scoped to a run_id.  Singleton per process."""

    _instance: SharedStateBus | None = None
    _init_lock = threading.Lock()

    def __new__(cls) -> SharedStateBus:
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._state: dict[str, dict[str, Any]] = {}
                cls._instance._events: dict[str, dict[str, threading.Event]] = {}
                cls._instance._lock = threading.Lock()
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────────

    def publish(
        self,
        run_id: str,
        agent_id: str,
        key: str,
        value: Any,
    ) -> None:
        """Publish a fact/finding to the shared state bus.

        Args:
            run_id: The run scope.
            agent_id: Which agent is publishing.
            key: State key (e.g. "research_results", "draft_v1").
            value: Arbitrary value.
        """
        with self._lock:
            if run_id not in self._state:
                self._state[run_id] = {}
            self._state[run_id][key] = {
                "value": value,
                "published_by": agent_id,
            }

            # Signal any waiters
            if run_id in self._events and key in self._events[run_id]:
                self._events[run_id][key].set()

        logger.debug(
            "SharedStateBus: agent '%s' published key '%s' for run '%s'",
            agent_id, key, run_id,
        )

    def subscribe(
        self,
        run_id: str,
        keys: list[str],
    ) -> dict[str, Any]:
        """Read current values for the requested keys.

        Args:
            run_id: The run scope.
            keys: List of keys to read.

        Returns:
            Dict mapping key -> value for keys that exist. Missing keys are omitted.
        """
        with self._lock:
            run_state = self._state.get(run_id, {})
            result: dict[str, Any] = {}
            for k in keys:
                entry = run_state.get(k)
                if entry is not None:
                    result[k] = entry["value"]
            return result

    def get_all(self, run_id: str) -> dict[str, Any]:
        """Return the full shared state dict for a run.

        Args:
            run_id: The run scope.

        Returns:
            Dict mapping key -> value for all published state in this run.
        """
        with self._lock:
            run_state = self._state.get(run_id, {})
            return {k: v["value"] for k, v in run_state.items()}

    def wait_for(
        self,
        run_id: str,
        key: str,
        timeout_seconds: float = 30,
    ) -> Any:
        """Block until the specified key is published, then return its value.

        Args:
            run_id: The run scope.
            key: The key to wait for.
            timeout_seconds: Max seconds to wait (default 30).

        Returns:
            The published value.

        Raises:
            TimeoutError: If the key is not published within the timeout.
        """
        # Fast path: already published
        with self._lock:
            run_state = self._state.get(run_id, {})
            entry = run_state.get(key)
            if entry is not None:
                return entry["value"]

            # Create event for waiting
            if run_id not in self._events:
                self._events[run_id] = {}
            if key not in self._events[run_id]:
                self._events[run_id][key] = threading.Event()
            event = self._events[run_id][key]

        # Block outside the lock
        signaled = event.wait(timeout=timeout_seconds)
        if not signaled:
            raise TimeoutError(
                f"SharedStateBus: timed out waiting for key '{key}' "
                f"in run '{run_id}' after {timeout_seconds}s"
            )

        # Retrieve the value
        with self._lock:
            return self._state[run_id][key]["value"]

    def cleanup(self, run_id: str) -> None:
        """Remove all state for a completed run.

        Args:
            run_id: The run scope to clean up.
        """
        with self._lock:
            self._state.pop(run_id, None)
            self._events.pop(run_id, None)

        logger.debug("SharedStateBus: cleaned up state for run '%s'", run_id)
