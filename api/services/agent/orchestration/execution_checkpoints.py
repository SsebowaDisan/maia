from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.services.agent.models import utc_now
from api.services.agent.planner import PlannedStep

from .role_contracts import resolve_owner_role_for_tool


@dataclass(slots=True, frozen=True)
class ExecutionCheckpoint:
    name: str
    status: str
    cycle: int
    step_cursor: int
    pending_steps: int
    active_role: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "cycle": self.cycle,
            "step_cursor": self.step_cursor,
            "pending_steps": self.pending_steps,
            "active_role": self.active_role,
            "timestamp": self.timestamp,
        }


def append_execution_checkpoint(
    *,
    settings: dict[str, Any],
    name: str,
    status: str = "in_progress",
    cycle: int = 0,
    step_cursor: int = 0,
    pending_steps: int = 0,
    active_role: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checkpoint = ExecutionCheckpoint(
        name=" ".join(str(name or "").split()).strip().lower() or "checkpoint",
        status=" ".join(str(status or "").split()).strip().lower() or "info",
        cycle=max(0, int(cycle)),
        step_cursor=max(0, int(step_cursor)),
        pending_steps=max(0, int(pending_steps)),
        active_role=" ".join(str(active_role or "").split()).strip().lower(),
        timestamp=utc_now().isoformat(),
    )
    payload = checkpoint.to_dict()
    if isinstance(metadata, dict) and metadata:
        payload["metadata"] = dict(metadata)
    history_raw = settings.get("__execution_checkpoints")
    history = list(history_raw) if isinstance(history_raw, list) else []
    history.append(payload)
    settings["__execution_checkpoints"] = history[-80:]
    settings["__execution_last_checkpoint"] = payload
    return payload


def build_role_dispatch_plan(*, steps: list[PlannedStep]) -> list[dict[str, Any]]:
    dispatch: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for index, step in enumerate(list(steps or []), start=1):
        role = resolve_owner_role_for_tool(step.tool_id)
        if not isinstance(current, dict) or str(current.get("role") or "") != role:
            current = {
                "role": role,
                "start_step": index,
                "end_step": index,
                "step_count": 1,
                "tool_ids": [step.tool_id],
            }
            dispatch.append(current)
            continue
        current["end_step"] = index
        current["step_count"] = int(current.get("step_count") or 0) + 1
        tool_ids = current.get("tool_ids")
        if not isinstance(tool_ids, list):
            tool_ids = []
            current["tool_ids"] = tool_ids
        if step.tool_id not in tool_ids:
            tool_ids.append(step.tool_id)
    return dispatch
