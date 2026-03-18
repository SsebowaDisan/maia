"""B2-03 — Gate engine.

Responsibility: intercept tool calls during agent execution, pause them for
human approval, and resume or cancel based on the decision.

The gate engine is stateless per-call — it reads GateConfig from the
AgentDefinitionSchema and blocks/approves tool calls accordingly.

Gate state is stored in-memory keyed by run_id for real-time signaling via
threading.Event objects. All gate state is also persisted to the database
via ``gate_store`` so that pending gates survive process restarts and
provide a full audit trail.

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
from api.services.agents import gate_store

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

    # Persist the pending gate so it survives restarts.
    try:
        gate_store.record_gate(
            run_id,
            gate_id,
            tenant_id=getattr(gate_config, "_tenant_id", ""),
            agent_id=getattr(gate_config, "_agent_id", ""),
            gate_type="tool_approval",
            description=f"Approval required for tool '{tool_id}'",
            timeout_seconds=timeout,
            fallback_action=str(fallback),
            metadata={**params_preview, "__tool_id__": tool_id},
        )
    except Exception:
        logger.warning("Failed to persist gate %s to store", gate_id, exc_info=True)

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


def approve_gate(run_id: str, gate_id: str, *, decided_by: str = "") -> bool:
    """Signal that an operator approved the gate.  Returns True if gate existed."""
    # Persist decision to durable store.
    try:
        gate_store.decide_gate(run_id, gate_id, "approve", decided_by=decided_by)
    except Exception:
        logger.warning("Failed to persist approve for gate %s", gate_id, exc_info=True)

    try:
        from api.services.audit.trail import record_event
        record_event(
            tenant_id="",
            user_id=decided_by,
            action="gate.approved",
            resource_type="gate",
            resource_id=gate_id,
            detail=f"Gate {gate_id} approved for run {run_id}",
        )
    except Exception:
        pass

    state = _run_states.get(run_id)
    if not state:
        return False
    return state.decide(gate_id, "approve")


def reject_gate(run_id: str, gate_id: str, *, decided_by: str = "") -> bool:
    """Signal that an operator rejected the gate.  Returns True if gate existed."""
    # Persist decision to durable store.
    try:
        gate_store.decide_gate(run_id, gate_id, "reject", decided_by=decided_by)
    except Exception:
        logger.warning("Failed to persist reject for gate %s", gate_id, exc_info=True)

    try:
        from api.services.audit.trail import record_event
        record_event(
            tenant_id="",
            user_id=decided_by,
            action="gate.rejected",
            resource_type="gate",
            resource_id=gate_id,
            detail=f"Gate {gate_id} rejected for run {run_id}",
        )
    except Exception:
        pass

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


# ── Recovery ───────────────────────────────────────────────────────────────────

def recover_pending_gates(run_id: str) -> list[GatePendingEvent]:
    """Reload pending gates from the durable store into in-memory state.

    Call this on startup (or when resuming a run) to restore gates that were
    waiting for a decision when the process last exited.  The returned list
    can be re-emitted as SSE events so the UI picks them up again.
    """
    import json as _json

    recovered: list[GatePendingEvent] = []
    try:
        records = gate_store.get_pending_gates(run_id=run_id)
    except Exception:
        logger.warning("Failed to recover pending gates for run %s", run_id, exc_info=True)
        return recovered

    state = _get_or_create_state(run_id)
    for rec in records:
        try:
            meta = _json.loads(rec.metadata_json) if rec.metadata_json else {}
        except Exception:
            meta = {}

        pending = GatePendingEvent(
            gate_id=rec.gate_id,
            run_id=rec.run_id,
            tool_id=meta.get("__tool_id__", rec.description.split("'")[1] if "'" in rec.description else "unknown"),
            params_preview=meta,
            created_at=rec.requested_at,
        )
        state.register(rec.gate_id, pending)
        recovered.append(pending)
        logger.info("Recovered pending gate %s for run %s", rec.gate_id, run_id)

    return recovered


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tool_needs_gate(tool_id: str, gate_config: Any) -> bool:
    if gate_config is None:
        return False
    gated_ids = getattr(gate_config, "tool_ids", None) or []
    if not gated_ids:
        return False
    return tool_id in gated_ids
