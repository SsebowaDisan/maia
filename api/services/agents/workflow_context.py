"""B7 — Per-run workflow shared context.

Responsibility: provide a lightweight, in-memory key-value store that is scoped
to a single workflow run.  All steps within the same run can read and write
shared state via the built-in context.read / context.write / context.append
tools without relying on external connectors like Google Sheets.

The context is stored only in process memory (a dict keyed by run_id) and is
automatically cleaned up when the run completes or fails.

Usage in workflow_executor.py:
    from api.services.agents.workflow_context import WorkflowRunContext
    ctx = WorkflowRunContext(run_id)
    ctx.write("lead_urls", ["https://example.com"])
    urls = ctx.read("lead_urls")   # → ["https://example.com"]
    ctx.append("lead_urls", "https://another.com")
    ctx.cleanup()
"""
from __future__ import annotations

import threading
from typing import Any

# Global in-memory registry:  run_id → dict
_contexts: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

_MAX_VALUE_BYTES = 512_000   # 512 KB per key
_MAX_KEYS = 100              # safety cap — prevents unbounded growth per run


class WorkflowContextError(Exception):
    pass


class WorkflowRunContext:
    """Scoped read/write context for one workflow run."""

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        with _lock:
            if run_id not in _contexts:
                _contexts[run_id] = {}

    # ── Public methods ────────────────────────────────────────────────────────

    def write(self, key: str, value: Any) -> None:
        """Store a value under key. Overwrites any existing value."""
        self._validate_key(key)
        encoded = _encode(value)
        if len(encoded) > _MAX_VALUE_BYTES:
            raise WorkflowContextError(
                f"Value for key '{key}' exceeds {_MAX_VALUE_BYTES} bytes."
            )
        with _lock:
            store = _contexts.get(self._run_id, {})
            if key not in store and len(store) >= _MAX_KEYS:
                raise WorkflowContextError(
                    f"Workflow context key limit ({_MAX_KEYS}) reached for run '{self._run_id}'."
                )
            store[key] = value
            _contexts[self._run_id] = store

    def read(self, key: str, default: Any = None) -> Any:
        """Retrieve a value by key. Returns default if key does not exist."""
        with _lock:
            return _contexts.get(self._run_id, {}).get(key, default)

    def append(self, key: str, item: Any) -> None:
        """Append item to a list stored at key.  Creates the list if absent."""
        with _lock:
            store = _contexts.get(self._run_id, {})
            existing = store.get(key)
            if existing is None:
                store[key] = [item]
            elif isinstance(existing, list):
                store[key] = existing + [item]
            else:
                raise WorkflowContextError(
                    f"Cannot append to key '{key}': existing value is not a list."
                )
            _contexts[self._run_id] = store

    def keys(self) -> list[str]:
        """Return all keys currently in the context."""
        with _lock:
            return list(_contexts.get(self._run_id, {}).keys())

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of the entire context dict for this run."""
        with _lock:
            return dict(_contexts.get(self._run_id, {}))

    def cleanup(self) -> None:
        """Remove this run's context from memory."""
        with _lock:
            _contexts.pop(self._run_id, None)

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_key(key: str) -> None:
        if not key or not key.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise WorkflowContextError(
                f"Context key '{key}' must be alphanumeric (underscores, hyphens, dots allowed)."
            )


# ── Module-level helpers ────────────────────────────────────────────────────────

def get_context(run_id: str) -> WorkflowRunContext:
    """Get or create the context for a workflow run."""
    return WorkflowRunContext(run_id)


def cleanup_context(run_id: str) -> None:
    """Remove the context for a completed/failed run."""
    with _lock:
        _contexts.pop(run_id, None)


def active_run_count() -> int:
    """Return number of runs with active context (for monitoring)."""
    with _lock:
        return len(_contexts)


def _encode(value: Any) -> bytes:
    """Estimate serialised size of a value."""
    import json
    try:
        return json.dumps(value).encode()
    except (TypeError, ValueError):
        return str(value).encode()
