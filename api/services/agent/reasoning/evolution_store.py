"""Evolution Store — cross-run self-learning via extracted lessons.

Inspired by AutoResearchClaw's evolution.py pattern.
Extracts lessons from workflow failures, retries, and quality issues.
Lessons are persisted as JSONL with time-decay weighting and
injected as prompt overlays into subsequent runs.

Usage:
    store = EvolutionStore(tenant_id="user123")
    store.record_lesson(category="analysis", lesson="Always verify currency symbols...", source_run_id="run_abc")
    overlay = store.get_prompt_overlay(stage="analysis", max_lessons=5)
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HALF_LIFE_DAYS = 30
MAX_AGE_DAYS = 90
MAX_LESSONS_PER_QUERY = 8

LESSON_CATEGORIES = {"system", "experiment", "writing", "analysis", "research", "pipeline", "data", "connector"}

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "analysis": ["data", "metric", "chart", "trend", "outlier", "correlation", "statistics", "kpi"],
    "writing": ["format", "tone", "grammar", "structure", "citation", "markdown", "report", "summary"],
    "research": ["search", "source", "literature", "reference", "finding", "evidence", "web"],
    "data": ["csv", "spreadsheet", "column", "row", "parse", "missing", "null", "type"],
    "connector": ["api", "oauth", "credential", "timeout", "rate limit", "connector", "integration"],
    "pipeline": ["workflow", "step", "retry", "timeout", "failed", "blocked", "sequence"],
}


def _infer_category(lesson: str, default: str = "system") -> str:
    """Infer lesson category from content using keyword scoring."""
    text = lesson.lower()
    scores: dict[str, int] = {}
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for kw in keywords if kw in text)
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else default


def _time_decay_weight(created_at: float) -> float:
    """Compute time-decay weight with 30-day half-life."""
    age_days = (time.time() - created_at) / 86400
    if age_days > MAX_AGE_DAYS:
        return 0.0
    return math.pow(0.5, age_days / HALF_LIFE_DAYS)


class EvolutionStore:
    """Persistent lesson store backed by JSONL files."""

    def __init__(self, tenant_id: str, base_dir: str | None = None):
        self.tenant_id = tenant_id
        if base_dir:
            self._dir = Path(base_dir) / tenant_id
        else:
            self._dir = Path(".maia_agent") / "evolution" / tenant_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "lessons.jsonl"

    def record_lesson(
        self,
        *,
        lesson: str,
        category: str | None = None,
        source_run_id: str = "",
        source_step_id: str = "",
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a lesson learned from a run."""
        if not lesson.strip():
            return {}
        resolved_category = category if category in LESSON_CATEGORIES else _infer_category(lesson)
        entry = {
            "lesson": lesson.strip(),
            "category": resolved_category,
            "severity": severity,
            "source_run_id": source_run_id,
            "source_step_id": source_step_id,
            "created_at": time.time(),
            "tenant_id": self.tenant_id,
            "metadata": metadata or {},
        }
        try:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("Failed to persist lesson: %s", exc)
        return entry

    def record_failure_lesson(
        self,
        *,
        step_id: str,
        error: str,
        run_id: str = "",
    ) -> dict[str, Any]:
        """Auto-extract a lesson from a step failure."""
        lesson = f"Step '{step_id}' failed with: {error[:300]}. Consider adding error handling or validation for this case."
        return self.record_lesson(
            lesson=lesson,
            severity="warning",
            source_run_id=run_id,
            source_step_id=step_id,
        )

    def record_retry_lesson(
        self,
        *,
        step_id: str,
        attempt: int,
        reason: str,
        run_id: str = "",
    ) -> dict[str, Any]:
        """Auto-extract a lesson from a retry."""
        lesson = f"Step '{step_id}' required {attempt} retries due to: {reason[:200]}. This step may need more robust input validation."
        return self.record_lesson(
            lesson=lesson,
            severity="info",
            source_run_id=run_id,
            source_step_id=step_id,
        )

    def get_lessons(
        self,
        *,
        category: str | None = None,
        max_results: int = MAX_LESSONS_PER_QUERY,
        min_weight: float = 0.1,
    ) -> list[dict[str, Any]]:
        """Retrieve lessons with time-decay weighting."""
        if not self._file.exists():
            return []
        lessons: list[dict[str, Any]] = []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if category and entry.get("category") != category:
                        continue
                    weight = _time_decay_weight(entry.get("created_at", 0))
                    if weight < min_weight:
                        continue
                    entry["_weight"] = round(weight, 4)
                    lessons.append(entry)
        except Exception as exc:
            logger.warning("Failed to read lessons: %s", exc)
            return []
        lessons.sort(key=lambda e: e.get("_weight", 0), reverse=True)
        return lessons[:max_results]

    def get_prompt_overlay(
        self,
        *,
        stage: str | None = None,
        max_lessons: int = 5,
    ) -> str:
        """Build a prompt overlay from relevant lessons.

        Returns a text block that can be prepended to agent prompts
        to inject cross-run learning.
        """
        category = None
        if stage:
            stage_lower = stage.lower()
            for cat in LESSON_CATEGORIES:
                if cat in stage_lower:
                    category = cat
                    break

        lessons = self.get_lessons(category=category, max_results=max_lessons)
        if not lessons:
            return ""

        lines = ["Based on previous runs, keep these lessons in mind:"]
        for i, entry in enumerate(lessons, 1):
            lines.append(f"{i}. {entry['lesson']}")
        return "\n".join(lines)

    def lesson_count(self) -> int:
        """Return total number of stored lessons."""
        if not self._file.exists():
            return 0
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    def clear_expired(self) -> int:
        """Remove lessons older than MAX_AGE_DAYS. Returns count removed."""
        if not self._file.exists():
            return 0
        kept: list[str] = []
        removed = 0
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if _time_decay_weight(entry.get("created_at", 0)) < 0.01:
                        removed += 1
                    else:
                        kept.append(json.dumps(entry, ensure_ascii=False))
            if removed > 0:
                tmp = self._file.with_suffix(".tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    for line in kept:
                        f.write(line + "\n")
                os.replace(str(tmp), str(self._file))
        except Exception as exc:
            logger.warning("Failed to clear expired lessons: %s", exc)
        return removed
