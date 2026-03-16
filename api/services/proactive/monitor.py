"""P5-04 — Proactive monitor orchestrator.

Responsibility: run signal checks for all active tenants on a periodic schedule
and fan out the resulting signals through the feed router.

Wires into the existing startup/shutdown lifecycle in api/main.py.
"""
from __future__ import annotations

import logging
import threading
from threading import Event, Thread

logger = logging.getLogger(__name__)

# Default poll interval: 15 minutes
_DEFAULT_INTERVAL_SECS = 900


class ProactiveMonitor:
    """Background thread that polls tenant signals and writes insights."""

    def __init__(self, interval_secs: int = _DEFAULT_INTERVAL_SECS) -> None:
        self._interval = interval_secs
        self._stop_event = Event()
        self._thread: Thread | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._loop,
            daemon=True,
            name="maia-proactive-monitor",
        )
        self._thread.start()
        logger.info("ProactiveMonitor started (interval=%ds)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._run_cycle()
            except Exception as exc:
                logger.error("ProactiveMonitor cycle failed: %s", exc, exc_info=True)

    def _run_cycle(self) -> None:
        tenants = self._list_tenants()
        if not tenants:
            return

        from .signal_detector import get_signal_detector
        from .feed_router import process_signals

        detector = get_signal_detector()
        for tenant_id in tenants:
            try:
                signals = detector.run_checks(tenant_id)
                if signals:
                    process_signals(signals)
                    logger.info(
                        "ProactiveMonitor: %d signals detected for tenant %s",
                        len(signals),
                        tenant_id,
                    )
            except Exception as exc:
                logger.warning(
                    "ProactiveMonitor: cycle failed for tenant %s: %s",
                    tenant_id,
                    exc,
                )

    @staticmethod
    def _list_tenants() -> list[str]:
        try:
            from api.services.tenants.store import list_tenants
            tenants = list_tenants(active_only=True)
            return [t.id for t in tenants]
        except Exception:
            return []

    # ── Manual trigger ────────────────────────────────────────────────────────

    def trigger_now(self, tenant_id: str | None = None) -> int:
        """Run one cycle immediately in the calling thread.

        Args:
            tenant_id: When given, only run checks for this tenant.

        Returns:
            Total number of signals detected.
        """
        from .signal_detector import get_signal_detector
        from .feed_router import process_signals

        detector = get_signal_detector()
        tenants = [tenant_id] if tenant_id else self._list_tenants()
        total = 0
        for tid in tenants:
            try:
                signals = detector.run_checks(tid)
                if signals:
                    process_signals(signals)
                    total += len(signals)
            except Exception as exc:
                logger.warning("trigger_now failed for tenant %s: %s", tid, exc)
        return total


_monitor: ProactiveMonitor | None = None
_monitor_lock = threading.Lock()


def get_proactive_monitor() -> ProactiveMonitor:
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = ProactiveMonitor()
    return _monitor
