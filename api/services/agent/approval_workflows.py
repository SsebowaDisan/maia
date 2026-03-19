"""Approval Workflows — enhanced gate system with action preview and edit.

Responsibility: before an agent executes a sensitive action (send email,
create purchase order, post to Slack), it pauses and presents a preview
of what it's about to do. The user can approve, edit, or reject.

This extends the existing gate system with:
- Rich action preview (not just "approve/reject" but "here's the email draft")
- Inline editing (user can modify the draft before approving)
- Auto-approve rules (skip approval for trusted actions)
- Audit log of all approval decisions
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

# Actions that require approval by default
SENSITIVE_ACTIONS = {
    "gmail.send", "outlook.send", "slack.send_message",
    "sap.create_purchase_order", "sap.post_goods_receipt",
    "invoice.create_invoice", "invoice.mark_paid",
    "google_ads.pause_campaign", "google_ads.update_bid",
}

# Actions that are always safe (never require approval)
SAFE_ACTIONS = {
    "gmail.read", "gmail.search", "outlook.read",
    "brave.search", "bing.search", "browser.navigate",
    "analytics.ga4.report", "analytics.ga4.full_report",
    "google_maps.geocode", "google_maps.places_search",
}


class ApprovalRequest:
    """A pending approval with action preview."""

    def __init__(
        self,
        *,
        gate_id: str = "",
        run_id: str = "",
        tool_id: str = "",
        action_label: str = "",
        preview: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        connector_id: str = "",
        risk_level: str = "medium",
    ):
        self.gate_id = gate_id or uuid.uuid4().hex[:12]
        self.run_id = run_id
        self.tool_id = tool_id
        self.action_label = action_label
        self.preview = preview or {}
        self.params = params or {}
        self.connector_id = connector_id
        self.risk_level = risk_level
        self.created_at = time.time()
        self.status = "pending"
        self.decision_at: float | None = None
        self.decided_by: str = ""
        self.edited_params: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "run_id": self.run_id,
            "tool_id": self.tool_id,
            "action_label": self.action_label,
            "preview": self.preview,
            "params": self.params,
            "connector_id": self.connector_id,
            "risk_level": self.risk_level,
            "status": self.status,
            "created_at": self.created_at,
            "decision_at": self.decision_at,
            "decided_by": self.decided_by,
            "edited_params": self.edited_params,
        }


class ApprovalWorkflowService:
    """Manages approval gates with rich previews."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[dict[str, Any]] = []
        self._auto_approve_rules: dict[str, bool] = {}

    def requires_approval(self, tool_id: str, tenant_id: str = "") -> bool:
        """Check if a tool action needs approval."""
        if tool_id in SAFE_ACTIONS:
            return False
        rule_key = f"{tenant_id}:{tool_id}" if tenant_id else tool_id
        if rule_key in self._auto_approve_rules:
            return not self._auto_approve_rules[rule_key]
        return tool_id in SENSITIVE_ACTIONS

    def create_gate(
        self,
        *,
        run_id: str,
        tool_id: str,
        params: dict[str, Any],
        connector_id: str = "",
    ) -> ApprovalRequest:
        """Create a new approval gate with action preview."""
        preview = _build_preview(tool_id, params)
        risk = "high" if tool_id in {"sap.create_purchase_order", "google_ads.update_bid"} else "medium"
        request = ApprovalRequest(
            run_id=run_id,
            tool_id=tool_id,
            action_label=_action_label(tool_id),
            preview=preview,
            params=params,
            connector_id=connector_id,
            risk_level=risk,
        )
        with self._lock:
            self._pending[request.gate_id] = request
        # Emit live event so UI shows the approval card
        _emit_approval_event(request)
        return request

    def approve(self, gate_id: str, user_id: str = "", edited_params: dict[str, Any] | None = None) -> ApprovalRequest | None:
        """Approve a pending gate, optionally with edited params."""
        with self._lock:
            request = self._pending.pop(gate_id, None)
            if not request:
                return None
            request.status = "approved"
            request.decision_at = time.time()
            request.decided_by = user_id
            if edited_params:
                request.edited_params = edited_params
            self._history.append(request.to_dict())
        return request

    def reject(self, gate_id: str, user_id: str = "", reason: str = "") -> ApprovalRequest | None:
        """Reject a pending gate."""
        with self._lock:
            request = self._pending.pop(gate_id, None)
            if not request:
                return None
            request.status = "rejected"
            request.decision_at = time.time()
            request.decided_by = user_id
            self._history.append({**request.to_dict(), "rejection_reason": reason})
        return request

    def list_pending(self, run_id: str = "") -> list[dict[str, Any]]:
        """List all pending approval gates."""
        with self._lock:
            gates = list(self._pending.values())
        if run_id:
            gates = [g for g in gates if g.run_id == run_id]
        return [g.to_dict() for g in gates]

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent approval decisions."""
        with self._lock:
            return list(reversed(self._history[-limit:]))

    def set_auto_approve(self, tool_id: str, auto: bool, tenant_id: str = "") -> None:
        """Set auto-approve rule for a tool action."""
        key = f"{tenant_id}:{tool_id}" if tenant_id else tool_id
        self._auto_approve_rules[key] = auto


def _build_preview(tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Build a human-readable preview of what the action will do."""
    if "send" in tool_id or "email" in tool_id:
        return {
            "type": "email",
            "to": params.get("to", ""),
            "subject": params.get("subject", ""),
            "body_preview": str(params.get("body", ""))[:500],
        }
    if "slack" in tool_id:
        return {
            "type": "message",
            "channel": params.get("channel", ""),
            "text_preview": str(params.get("text", ""))[:500],
        }
    if "purchase_order" in tool_id or "invoice" in tool_id:
        return {
            "type": "transaction",
            "summary": f"Create {tool_id.split('.')[-1].replace('_', ' ')}",
            "params_preview": {k: str(v)[:200] for k, v in list(params.items())[:5]},
        }
    return {"type": "action", "tool_id": tool_id, "params_preview": {k: str(v)[:100] for k, v in list(params.items())[:5]}}


def _action_label(tool_id: str) -> str:
    parts = tool_id.replace("_", " ").replace(".", " — ")
    return parts[:80]


def _emit_approval_event(request: ApprovalRequest) -> None:
    try:
        from api.services.agent.live_events import get_live_event_broker
        get_live_event_broker().publish(
            user_id="",
            run_id=request.run_id,
            event={
                "event_type": "approval_required",
                "title": f"Approval needed: {request.action_label}",
                "detail": json.dumps(request.preview, default=str)[:500],
                "stage": "execute",
                "status": "waiting",
                "data": request.to_dict(),
            },
        )
    except Exception:
        pass


_service: ApprovalWorkflowService | None = None


def get_approval_service() -> ApprovalWorkflowService:
    global _service
    if _service is None:
        _service = ApprovalWorkflowService()
    return _service
