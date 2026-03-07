from __future__ import annotations

from typing import Literal, cast

AgentRole = Literal[
    "conductor",
    "planner",
    "research",
    "browser",
    "document",
    "analyst",
    "writer",
    "verifier",
    "safety",
]

DEFAULT_AGENT_ROLE: AgentRole = "conductor"

_ROLE_SEQUENCE: tuple[AgentRole, ...] = (
    "conductor",
    "planner",
    "research",
    "browser",
    "document",
    "analyst",
    "writer",
    "verifier",
    "safety",
)

_ROLE_SET = set(_ROLE_SEQUENCE)

_ROLE_LABELS: dict[AgentRole, str] = {
    "conductor": "Conductor",
    "planner": "Planner",
    "research": "Research",
    "browser": "Browser",
    "document": "Document",
    "analyst": "Analyst",
    "writer": "Writer",
    "verifier": "Verifier",
    "safety": "Safety",
}

_ROLE_DESCRIPTIONS: dict[AgentRole, str] = {
    "conductor": "Owns run-level control flow, checkpointing, and role handoffs.",
    "planner": "Decomposes goals into role-owned, verifiable execution steps.",
    "research": "Finds and consolidates external sources and evidence.",
    "browser": "Executes live website interaction and structured page inspection.",
    "document": "Reads files and PDFs to extract grounded evidence.",
    "analyst": "Aggregates data, computes metrics, and produces structured analysis.",
    "writer": "Produces reports, drafts, and delivery-ready communication artifacts.",
    "verifier": "Checks contract completion, fact coverage, and output quality.",
    "safety": "Guards side effects, approvals, and human-verification boundaries.",
}


def list_agent_roles() -> tuple[AgentRole, ...]:
    return _ROLE_SEQUENCE


def is_agent_role(value: str | None) -> bool:
    normalized = " ".join(str(value or "").split()).strip().lower()
    return normalized in _ROLE_SET


def normalize_agent_role(value: str | None, *, default: AgentRole = DEFAULT_AGENT_ROLE) -> AgentRole:
    normalized = " ".join(str(value or "").split()).strip().lower()
    if normalized in _ROLE_SET:
        return cast(AgentRole, normalized)
    return default


def agent_role_label(role: AgentRole) -> str:
    return _ROLE_LABELS.get(role, _ROLE_LABELS[DEFAULT_AGENT_ROLE])


def agent_role_description(role: AgentRole) -> str:
    return _ROLE_DESCRIPTIONS.get(role, _ROLE_DESCRIPTIONS[DEFAULT_AGENT_ROLE])

