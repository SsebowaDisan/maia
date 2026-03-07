from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.services.agent.planner import PlannedStep

from .agent_roles import AgentRole
from .role_contracts import resolve_owner_role_for_tool


@dataclass(frozen=True, slots=True)
class RoleOwnedStep:
    step_index: int
    owner_role: AgentRole
    tool_id: str
    title: str
    why_this_step: str
    expected_evidence: tuple[str, ...]
    handoff_from_role: AgentRole | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "step": int(self.step_index),
            "owner_role": self.owner_role,
            "tool_id": self.tool_id,
            "title": self.title,
            "why_this_step": self.why_this_step,
            "expected_evidence": list(self.expected_evidence),
        }
        if self.handoff_from_role:
            payload["handoff_from_role"] = self.handoff_from_role
        return payload


def build_role_owned_steps(*, steps: list[PlannedStep]) -> list[RoleOwnedStep]:
    role_steps: list[RoleOwnedStep] = []
    previous_role: AgentRole | None = None
    for step_index, step in enumerate(steps, start=1):
        owner_role = resolve_owner_role_for_tool(step.tool_id)
        handoff_from_role = previous_role if previous_role and previous_role != owner_role else None
        role_steps.append(
            RoleOwnedStep(
                step_index=step_index,
                owner_role=owner_role,
                tool_id=str(step.tool_id or "").strip(),
                title=str(step.title or "").strip(),
                why_this_step=str(step.why_this_step or "").strip(),
                expected_evidence=tuple(str(item).strip() for item in step.expected_evidence if str(item).strip()),
                handoff_from_role=handoff_from_role,
            )
        )
        previous_role = owner_role
    return role_steps


def role_owned_steps_to_payload(*, steps: list[RoleOwnedStep]) -> list[dict[str, Any]]:
    return [row.to_payload() for row in steps]

