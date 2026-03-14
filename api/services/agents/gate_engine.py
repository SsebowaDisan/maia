"""B2-03 — Gate engine.

Responsibility: intercept tool calls during agent execution, pause them for
human approval, and resume or cancel based on the decision.

The gate engine is stateless per-call — it reads GateConfig from the
AgentDefinitionSchema and blocks/approves tool calls accordingly.

Gate state is stored in-memory keyed by run_id for the lifetime of a run.
Clients call ``approve_gate`` or ``reject_gate`` to unblock a pending gate.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from api.schemas.agent_definition.gate_config import GateFallbackAction

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes


@dataclass
class GatePendingEvent:
    gate_id: str
    run_id: str
    tool_id: str
    params_preview: dict[str, Any]
    created_at: float = field(default_factory=time.time)


class GateTimeoutError(Exception):
    pass


class GateRejectedError(Exception):
    pass


# ── Per-run gate state ──────────────────────────────────────────────────────────

class _GateState:
    """Holds the pending gates for one agent run."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # gate_id → Event (set = decision received)
        self._events: dict[str, threading.Event] = {}
        # gate_id → decision ("approve" | "reject")
        self._decisions: dict[str, str] = {}
        # gate_id → GatePendingEvent
        self.pending: dict[str, GatePendingEvent] = {}

    def register(self, gate_id: str, pending: GatePendingEvent) -> threading.Event:
        with self._lock:
            evt = threading.Event()
            self._events[gate_id] = evt
            self.pending[gate_id] = pending
        return evt

    def decide(self, gate_id: str, decision: str) -> bool:
        with self._lock:
            if gate_id not in self._events:
                return False
            self._decisions[gate_id] = decision
            self._events[gate_id].set()
            return True

    def get_decision(self, gate_id: str) -> Optional[str]:
        with self._lock:
            return self._decisions.get(gate_id)


# ── Registry of active run gate states ────────────────────────────────────────

_run_states: dict[str, _GateState] = {}
_registry_lock = threading.Lock()


def _get_or_create_state(run_id: str) -> _GateState:
    with _registry_lock:
        if run_id not in _run_states:
            _run_states[run_id] = _GateState()
        return _run_states[run_id]


def cleanup_run(run_id: str) -> None:
    """Remove gate state for a completed/cancelled run."""
    with _registry_lock:
        _run_states.pop(run_id, None)


# ── Public API ─────────────────────────────────────────────────────────────────

def check_gate(
    run_id: str,
    tool_id: str,
    params: dict[str, Any],
    *,
    gate_config: Any,  # GateConfig from AgentDefinitionSchema
    on_pending_event: Any = None,  # callable(GatePendingEvent) for SSE emission
) -> None:
    """Block execution until the gate is approved (or raise on reject/timeout).

    If ``gate_config`` has no gate for ``tool_id``, returns immediately.

    Args:
        run_id: Current agent run identifier.
        tool_id: The tool about to be called.
        params: Tool input parameters (truncated in pending event).
        gate_config: GateConfig instance from the agent definition.
        on_pending_event: Optional callback to emit the pending event for SSE.

    Raises:
        GateRejectedError: If the operator rejects the gate.
        GateTimeoutError: If timeout expires and fallback_action is "fail".
    """
    if not _tool_needs_gate(tool_id, gate_config):
        return

    gate_id = str(uuid.uuid4())
    timeout = getattr(gate_config, "timeout_seconds", _DEFAULT_TIMEOUT_SECONDS) or _DEFAULT_TIMEOUT_SECONDS
    fallback = getattr(gate_config, "fallback_action", "skip") or "skip"

    params_preview = {k: str(v)[:200] for k, v in (params or {}).items()}
    pending = GatePendingEvent(
        gate_id=gate_id,
        run_id=run_id,
        tool_id=tool_id,
        params_preview=params_preview,
    )

    state = _get_or_create_state(run_id)
    evt = state.register(gate_id, pending)

    if on_pending_event:
        try:
            on_pending_event(pending)
        except Exception:
            logger.debug("on_pending_event callback failed", exc_info=True)

    logger.info("Gate %s waiting for approval: run=%s tool=%s", gate_id, run_id, tool_id)

    approved = evt.wait(timeout=timeout)

    if not approved:
        # Timeout — BUG-06 fix: compare against GateFallbackAction enum
        if fallback == GateFallbackAction.abort:
            raise GateTimeoutError(f"Gate for tool '{tool_id}' timed out after {timeout}s.")
        # fallback == skip or auto_approve → caller should skip the tool call
        raise GateTimeoutError(f"__skip__:{tool_id}")

    decision = state.get_decision(gate_id)
    if decision == "reject":
        raise GateRejectedError(f"Gate for tool '{tool_id}' was rejected by operator.")
    # decision == "approve" → fall through and execute tool normally


def check_gates(
    run_id: str,
    tool_id: str,
    params: dict[str, Any],
    *,
    gates: list[Any],
    on_pending_event: Any = None,
) -> None:
    """Check tool_id against a list of GateConfig objects.

    Iterates all gate configs and blocks on the first matching gate.
    This is the correct entry point when using ``schema.gates`` (a list).
    """
    for gate_config in (gates or []):
        if _tool_needs_gate(tool_id, gate_config):
            check_gate(run_id, tool_id, params, gate_config=gate_config, on_pending_event=on_pending_event)
            return  # first matching gate wins


def approve_gate(run_id: str, gate_id: str) -> bool:
    """Signal that an operator approved the gate.  Returns True if gate existed."""
    state = _run_states.get(run_id)
    if not state:
        return False
    return state.decide(gate_id, "approve")


def reject_gate(run_id: str, gate_id: str) -> bool:
    """Signal that an operator rejected the gate.  Returns True if gate existed."""
    state = _run_states.get(run_id)
    if not state:
        return False
    return state.decide(gate_id, "reject")


def list_pending_gates(run_id: str) -> list[dict[str, Any]]:
    """Return all currently pending gates for a run."""
    state = _run_states.get(run_id)
    if not state:
        return []
    return [
        {
            "gate_id": p.gate_id,
            "tool_id": p.tool_id,
            "params_preview": p.params_preview,
            "waiting_since": p.created_at,
        }
        for p in state.pending.values()
        if not state._events.get(p.gate_id, threading.Event()).is_set()
    ]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tool_needs_gate(tool_id: str, gate_config: Any) -> bool:
    if gate_config is None:
        return False
    gated_ids = getattr(gate_config, "tool_ids", None) or []
    if not gated_ids:
        return False
    return tool_id in gated_ids
