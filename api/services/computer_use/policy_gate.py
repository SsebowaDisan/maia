"""Computer Use task policy gate.

Single responsibility:
- evaluate incoming Computer Use tasks against configurable policy rules.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

PolicyMode = Literal["off", "audit", "enforce"]

_DEFAULT_BLOCKED_TERMS = (
    "bypass 2fa",
    "steal credentials",
    "exfiltrate",
    "ransomware",
    "delete production database",
)


def _read_positive_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return max(1, default)
    try:
        parsed = int(raw)
    except ValueError:
        return max(1, default)
    return max(1, parsed)


def _read_mode() -> PolicyMode:
    raw = str(os.environ.get("MAIA_COMPUTER_USE_POLICY_MODE", "enforce")).strip().lower()
    if raw in {"off", "audit", "enforce"}:
        return raw  # type: ignore[return-value]
    return "enforce"


def _read_blocked_terms() -> tuple[str, ...]:
    raw = str(os.environ.get("MAIA_COMPUTER_USE_BLOCKED_TASK_TERMS", "")).strip()
    if not raw:
        return _DEFAULT_BLOCKED_TERMS
    terms: list[str] = []
    for candidate in raw.split(","):
        token = " ".join(str(candidate or "").strip().lower().split())
        if token:
            terms.append(token)
    return tuple(terms)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    mode: PolicyMode
    reason: str
    matched_terms: tuple[str, ...]
    max_task_chars: int


def evaluate_task_policy(task: str) -> PolicyDecision:
    mode = _read_mode()
    max_task_chars = _read_positive_int("MAIA_COMPUTER_USE_MAX_TASK_CHARS", 4000)
    normalized_task = " ".join(str(task or "").strip().split())

    if not normalized_task:
        return PolicyDecision(
            allowed=False,
            mode=mode,
            reason="Task must not be empty.",
            matched_terms=(),
            max_task_chars=max_task_chars,
        )

    if mode == "off":
        return PolicyDecision(
            allowed=True,
            mode=mode,
            reason="",
            matched_terms=(),
            max_task_chars=max_task_chars,
        )

    lowered = normalized_task.lower()
    matched_terms = tuple(
        term
        for term in _read_blocked_terms()
        if term and term in lowered
    )
    reason = ""
    if len(normalized_task) > max_task_chars:
        reason = (
            f"Task is too long ({len(normalized_task)} chars). "
            f"Maximum allowed is {max_task_chars}."
        )
    elif matched_terms:
        reason = (
            "Task matched blocked policy terms: "
            + ", ".join(matched_terms[:3])
            + "."
        )

    if not reason:
        return PolicyDecision(
            allowed=True,
            mode=mode,
            reason="",
            matched_terms=(),
            max_task_chars=max_task_chars,
        )

    if mode == "audit":
        return PolicyDecision(
            allowed=True,
            mode=mode,
            reason=reason,
            matched_terms=matched_terms,
            max_task_chars=max_task_chars,
        )

    return PolicyDecision(
        allowed=False,
        mode=mode,
        reason=reason,
        matched_terms=matched_terms,
        max_task_chars=max_task_chars,
    )


def get_policy_snapshot() -> dict[str, object]:
    terms = _read_blocked_terms()
    return {
        "mode": _read_mode(),
        "max_task_chars": _read_positive_int("MAIA_COMPUTER_USE_MAX_TASK_CHARS", 4000),
        "blocked_terms_count": len(terms),
        "blocked_terms_preview": list(terms[:10]),
    }
