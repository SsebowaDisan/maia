"""Task worker — long-running process that executes queued tasks.

Usage:
    python -m api.services.tasks.worker
"""
from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Any, Callable

from api.services.tasks.queue import TaskQueue, get_task_queue

logger = logging.getLogger(__name__)


class TaskWorker:
    """Pull tasks from a queue and dispatch them to registered handlers.

    Parameters
    ----------
    queue:
        The :class:`TaskQueue` to consume from.
    concurrency:
        Number of worker threads to run in parallel.
    """

    def __init__(self, queue: TaskQueue, concurrency: int = 4) -> None:
        self._queue = queue
        self._concurrency = concurrency
        self._handlers: dict[str, Callable[[dict], Any]] = {}
        self._threads: list[threading.Thread] = []
        self._running = threading.Event()

    # -- handler registration -----------------------------------------------

    def register_handler(self, task_type: str, handler: Callable[[dict], Any]) -> None:
        """Register *handler* as the executor for *task_type*."""
        self._handlers[task_type] = handler
        logger.info("Registered handler for %s", task_type)

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Spawn worker threads and begin processing."""
        if not self._handlers:
            raise RuntimeError("No handlers registered — call register_handler first")
        self._running.set()
        task_types = list(self._handlers)
        for idx in range(self._concurrency):
            t = threading.Thread(
                target=self._worker_loop,
                args=(task_types,),
                name=f"task-worker-{idx}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)
        logger.info(
            "TaskWorker started: %d threads, task_types=%s",
            self._concurrency,
            task_types,
        )

    def stop(self, timeout: float = 10) -> None:
        """Signal all worker threads to stop and wait up to *timeout* seconds."""
        logger.info("Stopping TaskWorker ...")
        self._running.clear()
        deadline = time.time() + timeout
        for t in self._threads:
            remaining = max(0, deadline - time.time())
            t.join(timeout=remaining)
        self._threads.clear()
        logger.info("TaskWorker stopped.")

    # -- internal -----------------------------------------------------------

    def _worker_loop(self, task_types: list[str]) -> None:
        while self._running.is_set():
            item = self._queue.dequeue(task_types, timeout_s=2)
            if item is None:
                continue
            task_id, task_type, payload = item
            handler = self._handlers.get(task_type)
            if handler is None:
                self._queue.nack(task_id, error=f"No handler for {task_type}")
                logger.error("No handler for task_type=%s (task_id=%s)", task_type, task_id)
                continue
            try:
                logger.info("Executing %s task_id=%s", task_type, task_id)
                handler(payload)
                self._queue.ack(task_id)
                logger.info("Completed task_id=%s", task_id)
            except Exception as exc:
                self._queue.nack(task_id, error=str(exc))
                logger.exception("Failed task_id=%s: %s", task_id, exc)


# ---------------------------------------------------------------------------
# Handler imports (lazy to avoid circular deps at module level)
# ---------------------------------------------------------------------------

def _import_handlers() -> dict[str, Callable[[dict], Any]]:
    """Import and return the mapping of task_type → handler callable."""
    handlers: dict[str, Callable[[dict], Any]] = {}

    try:
        from api.services.agents.workflow_executor import handle_run_step
        handlers["workflow.run_step"] = handle_run_step
    except ImportError:
        logger.warning("workflow_executor not available — workflow.run_step disabled")

    try:
        from api.services.agents.scheduler import handle_scheduled_run
        handlers["agent.scheduled_run"] = handle_scheduled_run
    except ImportError:
        logger.warning("scheduler not available — agent.scheduled_run disabled")

    try:
        from api.services.agents.event_triggers import handle_event_run
        handlers["agent.event_run"] = handle_event_run
    except ImportError:
        logger.warning("event_triggers not available — agent.event_run disabled")

    return handlers


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    q = get_task_queue()
    worker = TaskWorker(q, concurrency=4)

    handlers = _import_handlers()
    if not handlers:
        logger.error("No task handlers could be imported — exiting.")
        return
    for task_type, handler in handlers.items():
        worker.register_handler(task_type, handler)

    shutdown = threading.Event()

    def _on_signal(signum: int, _frame: Any) -> None:
        logger.info("Received signal %s — shutting down", signum)
        shutdown.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    worker.start()
    logger.info("Worker running. Press Ctrl+C to stop.")
    shutdown.wait()
    worker.stop()


if __name__ == "__main__":
    main()
