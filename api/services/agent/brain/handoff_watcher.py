"""Idle-handoff watchdog for one agent turn.

Starts a daemon ``threading.Timer`` when the Brain is first constructed.
If no step completes within `timeout_seconds`, the watcher fires:
  - Sets ``handoff_flag`` in the shared settings dict so the step executor's
    ``is_handoff_paused()`` check triggers and the turn suspends gracefully.
  - Logs a warning so ops can monitor timeout rates.

The watcher is cancelled on Brain.observe_step() so it only fires when
the agent is genuinely stuck between steps.

Environment
-----------
MAIA_HANDOFF_TIMEOUT_SECONDS   (default "120") — idle seconds before pause
MAIA_HANDOFF_WATCHER_ENABLED   (default "true") — set "false" to disable
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = int(os.environ.get("MAIA_HANDOFF_TIMEOUT_SECONDS", "120"))
_ENABLED = os.environ.get("MAIA_HANDOFF_WATCHER_ENABLED", "true").lower() != "false"

# Key injected into execution_context.settings to trigger is_handoff_paused().
_HANDOFF_FLAG_KEY = "__handoff_pause_requested"


class HandoffWatcher:
    """One-shot idle watcher tied to a single agent turn.

    Usage::

        watcher = HandoffWatcher(settings=execution_context.settings)
        watcher.start()
        # ... after each step outcome:
        watcher.reset()   # restart the idle timer
        # ... when turn completes:
        watcher.cancel()
    """

    def __init__(
        self,
        *,
        settings: dict[str, Any],
        timeout_seconds: int = _TIMEOUT_SECONDS,
        run_id: str = "",
    ) -> None:
        self._settings = settings
        self._timeout = timeout_seconds
        self._run_id = run_id
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._fired = False

    def start(self) -> None:
        """Arm the watcher. Call once after plan is ready."""
        if not _ENABLED:
            return
        self._arm()

    def reset(self) -> None:
        """Restart the idle timer (call after every step outcome)."""
        if not _ENABLED:
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._fired = False
        self._arm()

    def cancel(self) -> None:
        """Disarm the watcher (call when the turn completes normally)."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    @property
    def has_fired(self) -> bool:
        return self._fired

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _arm(self) -> None:
        timer = threading.Timer(
            interval=self._timeout,
            function=self._on_timeout,
        )
        timer.daemon = True
        timer.start()
        with self._lock:
            self._timer = timer

    def _on_timeout(self) -> None:
        with self._lock:
            self._fired = True
            self._timer = None
        logger.warning(
            "brain.handoff_watcher.idle_timeout run_id=%s timeout_s=%d",
            self._run_id,
            self._timeout,
        )
        # Signal the step executor to pause gracefully.
        self._settings[_HANDOFF_FLAG_KEY] = True
        self._settings.setdefault("__handoff_pause_reason", "brain_idle_timeout")
        self._settings.setdefault(
            "__handoff_pause_detail",
            f"Agent idle for {self._timeout}s — pausing for human verification.",
        )
