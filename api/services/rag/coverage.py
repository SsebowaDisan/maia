"""RAG Pipeline Phase 11: Coverage Check — assess if evidence answers the query.

Analyzes the ranked evidence to determine:
  - SUFFICIENT: evidence fully covers the query
  - PARTIAL: some aspects answered, gaps remain
  - CONFLICTING: sources disagree on key facts
  - INSUFFICIENT: not enough evidence
  - MATH_READY: calculation query with all variable values found
  - MATH_INCOMPLETE: calculation query with missing variables

Uses rule-based analysis (no LLM call) so it is fast and deterministic.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from api.services.rag.types import (
    CoverageResult,
    CoverageVerdict,
    RAGConfig,
    RankedEvidence,
)

logger = logging.getLogger(__name__)


# ── Query analysis ──────────────────────────────────────────────────────────

_MATH_KEYWORDS = frozenset({
    "calculate", "compute", "formula", "equation", "solve", "derive",
    "what is the value", "how much", "find the", "evaluate",
    "sum", "total", "average", "mean", "percentage", "ratio",
})

_MATH_PATTERN = re.compile(
    r"(calculate|compute|solve|evaluate|find|what is|how much|how many)",
    re.IGNORECASE,
)

_VARIABLE_PATTERN = re.compile(
    r"([A-Z])\s*=\s*([0-9.,]+(?:\s*[a-zA-Z/%]+)?)",
)

_FORMULA_PATTERN = re.compile(
    r"([A-Z])\s*=\s*[A-Z\s*/+\-()]+",
)


def _is_math_query(query: str) -> bool:
    """Detect if the query is asking for a calculation."""
    query_lower = query.lower()
    if _MATH_PATTERN.search(query_lower):
        return True
    for kw in _MATH_KEYWORDS:
        if kw in query_lower:
            return True
    return False


def _extract_query_aspects(query: str) -> list[str]:
    """Break a query into its key informational aspects.

    Uses a simple heuristic: split on conjunctions and question words,
    then extract noun phrases. Returns a list of aspect strings.
    """
    # Split on common query delimiters
    parts = re.split(r"\b(?:and|or|also|additionally|as well as|,)\b", query, flags=re.IGNORECASE)
    aspects: list[str] = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Remove question prefixes
        cleaned = re.sub(
            r"^(what|who|where|when|why|how|is|are|was|were|do|does|did|can|could|will|would|should)\s+",
            "", part, flags=re.IGNORECASE,
        ).strip()
        if cleaned and len(cleaned) > 3:
            aspects.append(cleaned)

    # If no aspects extracted, use the full query
    if not aspects:
        aspects = [query.strip()]

    return aspects


# ── Evidence analysis ───────────────────────────────────────────────────────

def _check_aspect_coverage(
    aspects: list[str],
    evidence: list[RankedEvidence],
) -> tuple[list[str], list[str]]:
    """Check which query aspects are covered by evidence.

    Returns (answered_aspects, missing_aspects).
    """
    answered: list[str] = []
    missing: list[str] = []

    for aspect in aspects:
        aspect_tokens = set(re.findall(r"[a-z0-9]+", aspect.lower()))
        if len(aspect_tokens) < 2:
            # Very short aspect — skip
            answered.append(aspect)
            continue

        covered = False
        for ev in evidence:
            ev_tokens = set(re.findall(r"[a-z0-9]+", ev.chunk.text.lower()))
            overlap = len(aspect_tokens & ev_tokens) / max(len(aspect_tokens), 1)
            if overlap >= 0.4:
                covered = True
                break

        if covered:
            answered.append(aspect)
        else:
            missing.append(aspect)

    return answered, missing


def _detect_conflicts(evidence: list[RankedEvidence]) -> list[str]:
    """Detect factual conflicts between evidence chunks.

    Looks for numerical contradictions: different numbers associated
    with the same entity/context across different sources.
    """
    conflicts: list[str] = []

    # Extract number-context pairs from each source
    source_facts: dict[str, list[tuple[str, str]]] = defaultdict(list)
    number_pattern = re.compile(r"(\b\d+(?:\.\d+)?(?:\s*%)?)\s+(\w+(?:\s+\w+){0,3})")

    for ev in evidence:
        matches = number_pattern.findall(ev.chunk.text)
        for value, context in matches:
            source_facts[ev.chunk.source_id].append((value.strip(), context.strip().lower()))

    # Compare facts across different sources
    source_ids = list(source_facts.keys())
    for i in range(len(source_ids)):
        for j in range(i + 1, len(source_ids)):
            facts_a = source_facts[source_ids[i]]
            facts_b = source_facts[source_ids[j]]
            for val_a, ctx_a in facts_a:
                for val_b, ctx_b in facts_b:
                    # Same context, different values
                    ctx_overlap = set(ctx_a.split()) & set(ctx_b.split())
                    if len(ctx_overlap) >= 2 and val_a != val_b:
                        conflict = (
                            f"Source {source_ids[i]} says '{val_a} {ctx_a}' "
                            f"but source {source_ids[j]} says '{val_b} {ctx_b}'"
                        )
                        conflicts.append(conflict)

    return conflicts[:5]  # Cap at 5 to avoid noise


def _check_math_coverage(
    evidence: list[RankedEvidence],
) -> tuple[dict[str, str], list[str]]:
    """Extract formula variables and check if all are present in evidence.

    Returns (found_variables, missing_variable_names).
    """
    all_text = " ".join(ev.chunk.text for ev in evidence)

    # Extract variable assignments (e.g. "P = 101325 Pa")
    found_vars: dict[str, str] = {}
    for match in _VARIABLE_PATTERN.finditer(all_text):
        var_name = match.group(1)
        var_value = match.group(2).strip()
        found_vars[var_name] = var_value

    # Also extract from FormulaSpans
    for ev in evidence:
        for formula in ev.chunk.formulas:
            for var_name, var_desc in formula.variables.items():
                if var_name not in found_vars:
                    found_vars[var_name] = var_desc

    # Find formulas and extract required variables
    required_vars: set[str] = set()
    for match in _FORMULA_PATTERN.finditer(all_text):
        formula_text = match.group(0)
        # Extract single-letter variable names from the right side
        rhs = formula_text.split("=", 1)[1] if "=" in formula_text else ""
        for var in re.findall(r"[A-Z]", rhs):
            required_vars.add(var)

    # Check which required variables are missing
    missing = [v for v in sorted(required_vars) if v not in found_vars]

    return found_vars, missing


# ── Public API ──────────────────────────────────────────────────────────────

async def check_coverage(
    query: str,
    evidence: list[RankedEvidence],
    config: RAGConfig,
) -> CoverageResult:
    """Phase 11: Analyze whether evidence sufficiently answers the query.

    Parameters
    ----------
    query : the user's question
    evidence : ranked evidence from Phase 10
    config : pipeline configuration

    Returns
    -------
    CoverageResult with verdict, answered/missing aspects, conflicts, etc.
    """
    if not evidence:
        return CoverageResult(
            verdict=CoverageVerdict.INSUFFICIENT,
            missing_aspects=[query],
            confidence=0.0,
        )

    # Break query into aspects and check coverage
    aspects = _extract_query_aspects(query)
    answered, missing = _check_aspect_coverage(aspects, evidence)

    # Detect conflicts between sources
    conflicts = _detect_conflicts(evidence) if len(evidence) >= 2 else []

    # Check for math queries
    is_math = _is_math_query(query)
    math_vars: dict[str, str] = {}
    math_missing: list[str] = []

    if is_math and config.allow_calculations:
        math_vars, math_missing = _check_math_coverage(evidence)

    # ── Determine verdict ───────────────────────────────────────────────
    if is_math and config.allow_calculations:
        if math_missing:
            verdict = CoverageVerdict.MATH_INCOMPLETE
        else:
            verdict = CoverageVerdict.MATH_READY
    elif conflicts:
        verdict = CoverageVerdict.CONFLICTING
    elif not missing:
        verdict = CoverageVerdict.SUFFICIENT
    elif answered and missing:
        verdict = CoverageVerdict.PARTIAL
    else:
        verdict = CoverageVerdict.INSUFFICIENT

    # Confidence: based on coverage ratio and top evidence scores
    coverage_ratio = len(answered) / max(len(aspects), 1)
    avg_score = sum(ev.final_score for ev in evidence) / max(len(evidence), 1)
    confidence = coverage_ratio * 0.6 + min(avg_score, 1.0) * 0.4

    result = CoverageResult(
        verdict=verdict,
        answered_aspects=answered,
        missing_aspects=missing,
        conflicts=conflicts,
        math_variables=math_vars,
        math_missing=math_missing,
        confidence=round(confidence, 3),
    )

    logger.info(
        "Coverage: verdict=%s, answered=%d/%d, conflicts=%d, confidence=%.3f",
        verdict.value, len(answered), len(aspects), len(conflicts), confidence,
    )

    return result
