"""Automated Trace Learning (Innovation #3).

Examines completed run traces to extract reusable rules about tool
effectiveness, failure modes, and successful tool sequences.

Tables
------
  maia_learned_rule  -- one row per extracted rule
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import Counter, defaultdict
from typing import Any, Optional

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ORM
# ---------------------------------------------------------------------------

class LearnedRule(SQLModel, table=True):
    __tablename__ = "maia_learned_rule"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    agent_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    rule_text: str = ""
    recommendation: str = ""
    confidence: float = 0.0
    occurrences: int = 0
    tool_id: str = Field(default="", index=True)
    failure_pattern: str = ""
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# Known failure classification
# ---------------------------------------------------------------------------

_FAILURE_PATTERNS = {
    "timeout": ["timeout", "timed out", "deadline exceeded", "read timeout"],
    "auth": ["401", "403", "unauthorized", "forbidden", "auth", "login required"],
    "empty_result": ["no results", "empty", "nothing found", "0 results"],
    "rate_limit": ["429", "rate limit", "too many requests", "throttled"],
    "not_found": ["404", "not found", "does not exist"],
    "server_error": ["500", "502", "503", "internal server error", "bad gateway"],
}


def _classify_failure(error_msg: str, outcome_status: str) -> str:
    """Classify a failure into a known pattern category."""
    if outcome_status == "empty":
        return "empty_result"
    lower = error_msg.lower() if error_msg else ""
    for pattern_name, keywords in _FAILURE_PATTERNS.items():
        for kw in keywords:
            if kw in lower:
                return pattern_name
    return "unknown" if outcome_status == "failed" else ""


# ---------------------------------------------------------------------------
# TraceLearner
# ---------------------------------------------------------------------------

class TraceLearner:
    """Learns reusable rules from completed execution traces."""

    def analyze_run_trace(
        self,
        run_id: str,
        steps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Examine a completed run's steps and extract patterns.

        Parameters
        ----------
        run_id : str
            Identifier of the completed run.
        steps : list[dict]
            Each dict should have at minimum: tool_id, outcome_status,
            error_message (optional), evidence_summary (optional),
            step_index (optional).

        Returns
        -------
        list[dict]
            Patterns found in this trace.
        """
        if not steps:
            return []

        patterns: list[dict[str, Any]] = []

        # --- Tool success/failure tracking ---
        tool_outcomes: dict[str, list[str]] = defaultdict(list)
        tool_errors: dict[str, list[str]] = defaultdict(list)
        sequence: list[str] = []

        for step in steps:
            tool_id = str(step.get("tool_id", ""))
            status = str(step.get("outcome_status", ""))
            error = str(step.get("error_message", ""))
            evidence = str(step.get("evidence_summary", ""))

            if not tool_id:
                continue

            tool_outcomes[tool_id].append(status)
            sequence.append(tool_id)

            if status in ("failed", "blocked", "empty"):
                failure_type = _classify_failure(error, status)
                if failure_type:
                    tool_errors[tool_id].append(failure_type)
                patterns.append({
                    "type": "tool_failure",
                    "run_id": run_id,
                    "tool_id": tool_id,
                    "failure_pattern": failure_type,
                    "error_preview": error[:200],
                })

        # --- Successful sequences (pairs that both succeeded) ---
        for i in range(len(sequence) - 1):
            tool_a = sequence[i]
            tool_b = sequence[i + 1]
            status_a = str(steps[i].get("outcome_status", ""))
            status_b = str(steps[i + 1].get("outcome_status", ""))
            if status_a == "success" and status_b == "success":
                patterns.append({
                    "type": "successful_sequence",
                    "run_id": run_id,
                    "tool_a": tool_a,
                    "tool_b": tool_b,
                })

        # --- Evidence quality patterns ---
        for step in steps:
            tool_id = str(step.get("tool_id", ""))
            evidence = str(step.get("evidence_summary", ""))
            status = str(step.get("outcome_status", ""))
            if status == "success" and len(evidence) > 200:
                patterns.append({
                    "type": "high_quality_evidence",
                    "run_id": run_id,
                    "tool_id": tool_id,
                    "evidence_length": len(evidence),
                })

        return patterns

    def extract_rules(
        self,
        agent_id: str,
        tenant_id: str,
        min_occurrences: int = 3,
    ) -> list[dict[str, Any]]:
        """Extract learned rules from accumulated pattern data.

        Queries the LearnedRule table and returns rules that meet the
        minimum occurrence threshold.
        """
        _ensure_tables()
        with Session(engine) as session:
            rows = session.exec(
                select(LearnedRule)
                .where(LearnedRule.agent_id == agent_id)
                .where(LearnedRule.tenant_id == tenant_id)
                .where(LearnedRule.occurrences >= min_occurrences)
                .order_by(LearnedRule.confidence.desc())  # type: ignore[arg-type]
            ).all()

        return [
            {
                "rule": r.rule_text,
                "recommendation": r.recommendation,
                "confidence": r.confidence,
                "occurrences": r.occurrences,
                "tool_id": r.tool_id,
                "failure_pattern": r.failure_pattern,
            }
            for r in rows
        ]

    def persist_patterns(
        self,
        agent_id: str,
        tenant_id: str,
        patterns: list[dict[str, Any]],
    ) -> int:
        """Persist extracted patterns as learned rules (upsert by tool + pattern).

        Returns the number of rules created or updated.
        """
        _ensure_tables()
        if not patterns:
            return 0

        # Aggregate patterns by (tool_id, failure_pattern/type)
        aggregated: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for p in patterns:
            p_type = str(p.get("type", ""))
            tool_id = str(p.get("tool_id", ""))
            if p_type == "tool_failure":
                key = (tool_id, str(p.get("failure_pattern", "")))
            elif p_type == "successful_sequence":
                key = (str(p.get("tool_a", "")), f"sequence_to_{p.get('tool_b', '')}")
            else:
                key = (tool_id, p_type)
            aggregated[key].append(p)

        count = 0
        now = time.time()
        with Session(engine) as session:
            for (tool_id, pattern_key), group in aggregated.items():
                # Check for existing rule
                existing = session.exec(
                    select(LearnedRule)
                    .where(LearnedRule.agent_id == agent_id)
                    .where(LearnedRule.tenant_id == tenant_id)
                    .where(LearnedRule.tool_id == tool_id)
                    .where(LearnedRule.failure_pattern == pattern_key)
                ).first()

                if existing:
                    existing.occurrences += len(group)
                    existing.confidence = min(
                        0.95, existing.occurrences / (existing.occurrences + 5)
                    )
                    existing.updated_at = now
                    session.add(existing)
                else:
                    rule_text = _build_rule_text(group[0])
                    recommendation = _build_recommendation(group[0])
                    occ = len(group)
                    rule = LearnedRule(
                        agent_id=agent_id,
                        tenant_id=tenant_id,
                        rule_text=rule_text,
                        recommendation=recommendation,
                        confidence=occ / (occ + 5),
                        occurrences=occ,
                        tool_id=tool_id,
                        failure_pattern=pattern_key,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(rule)
                count += 1

            session.commit()

        return count

    def get_tool_recommendations(
        self,
        tool_id: str,
        context_summary: str,
    ) -> list[dict[str, Any]]:
        """Return recommendations for a tool based on learned patterns.

        Queries all rules for this tool_id across all agents/tenants
        and returns suggestions sorted by confidence.
        """
        _ensure_tables()
        with Session(engine) as session:
            rows = session.exec(
                select(LearnedRule)
                .where(LearnedRule.tool_id == tool_id)
                .where(LearnedRule.occurrences >= 2)
                .order_by(LearnedRule.confidence.desc())  # type: ignore[arg-type]
                .limit(10)
            ).all()

        return [
            {
                "rule": r.rule_text,
                "recommendation": r.recommendation,
                "confidence": r.confidence,
                "occurrences": r.occurrences,
                "failure_pattern": r.failure_pattern,
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_rule_text(pattern: dict[str, Any]) -> str:
    p_type = pattern.get("type", "")
    tool_id = pattern.get("tool_id", "")
    if p_type == "tool_failure":
        fp = pattern.get("failure_pattern", "unknown")
        return f"{tool_id} fails with {fp}"
    if p_type == "successful_sequence":
        return f"{pattern.get('tool_a', '')} followed by {pattern.get('tool_b', '')} succeeds"
    if p_type == "high_quality_evidence":
        return f"{tool_id} produces high-quality evidence"
    return f"{tool_id}: {p_type}"


def _build_recommendation(pattern: dict[str, Any]) -> str:
    p_type = pattern.get("type", "")
    fp = pattern.get("failure_pattern", "")
    if p_type == "tool_failure":
        recs = {
            "timeout": "increase timeout or use a lighter-weight alternative",
            "auth": "verify credentials or use browser_playwright for authenticated sites",
            "empty_result": "broaden search query or try an alternative data source",
            "rate_limit": "add delay between requests or use cached results",
            "not_found": "verify URL/resource exists before requesting",
            "server_error": "retry with backoff or use an alternative endpoint",
        }
        return recs.get(fp, "investigate root cause and consider alternative tools")
    if p_type == "successful_sequence":
        return f"use {pattern.get('tool_a', '')} before {pattern.get('tool_b', '')} for best results"
    return "continue using this approach"
