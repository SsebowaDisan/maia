"""Quality Gate — detects template/placeholder text and incomplete output.

Inspired by AutoResearchClaw's quality assessment pattern.
Scans agent output for placeholder patterns, generic filler text,
and structural issues. Blocks publishing if quality is below threshold.

Usage:
    result = check_output_quality(text="The analysis shows that [INSERT DATA HERE]...")
    if not result["passed"]:
        print("Quality issues:", result["issues"])
"""
from __future__ import annotations

import re
from typing import Any

# ── Placeholder patterns ──────────────────────────────────────────────────────

_BRACKET_PLACEHOLDER = re.compile(r"\[(?:INSERT|ADD|TODO|PLACEHOLDER|YOUR|FILL|EDIT|REPLACE|TBD)[^\]]*\]", re.IGNORECASE)
_ANGLE_PLACEHOLDER = re.compile(r"<(?:INSERT|ADD|TODO|PLACEHOLDER|YOUR|FILL|EDIT|REPLACE)[^>]*>", re.IGNORECASE)
_CURLY_PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}")
_LOREM_IPSUM = re.compile(r"lorem\s+ipsum", re.IGNORECASE)
_WILL_DESCRIBE = re.compile(r"(?:this\s+section\s+will|we\s+will\s+(?:discuss|describe|explain|cover)\s+this)", re.IGNORECASE)
_GENERIC_FILLER = re.compile(r"(?:as\s+(?:mentioned|noted|discussed)\s+(?:above|below|earlier|previously))\s*[.,]", re.IGNORECASE)
_SAMPLE_DATA = re.compile(r"(?:example|sample|dummy|test)\s+data", re.IGNORECASE)
_ELLIPSIS_PLACEHOLDER = re.compile(r"\.\.\.\s*(?:\[|$)")

_ALL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("bracket_placeholder", _BRACKET_PLACEHOLDER),
    ("angle_placeholder", _ANGLE_PLACEHOLDER),
    ("curly_placeholder", _CURLY_PLACEHOLDER),
    ("lorem_ipsum", _LOREM_IPSUM),
    ("deferred_content", _WILL_DESCRIBE),
    ("sample_data", _SAMPLE_DATA),
    ("ellipsis_placeholder", _ELLIPSIS_PLACEHOLDER),
]

# Filler is tracked separately (lower severity)
_FILLER_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("generic_filler", _GENERIC_FILLER),
]

# ── Structural checks ────────────────────────────────────────────────────────

_MIN_CONTENT_LENGTH = 100
_MIN_PARAGRAPHS = 2
_MAX_TEMPLATE_RATIO = 0.05


def check_output_quality(
    text: str,
    *,
    max_template_ratio: float = _MAX_TEMPLATE_RATIO,
    min_length: int = _MIN_CONTENT_LENGTH,
    min_paragraphs: int = _MIN_PARAGRAPHS,
) -> dict[str, Any]:
    """Evaluate output quality.

    Returns:
        dict with: passed (bool), score (0-1), issues (list), template_ratio, stats
    """
    if not text or not text.strip():
        return {
            "passed": False,
            "score": 0.0,
            "issues": [{"type": "empty", "severity": "critical", "message": "Output is empty"}],
            "template_ratio": 1.0,
            "stats": {},
        }

    issues: list[dict[str, str]] = []
    content = text.strip()
    total_chars = len(content)
    template_chars = 0

    # Check placeholder patterns
    for name, pattern in _ALL_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            match_chars = sum(len(m) for m in matches)
            template_chars += match_chars
            issues.append({
                "type": name,
                "severity": "critical",
                "message": f"Found {len(matches)} {name.replace('_', ' ')} pattern(s)",
                "examples": [str(m)[:80] for m in matches[:3]],
            })

    # Check filler patterns (lower severity)
    for name, pattern in _FILLER_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            issues.append({
                "type": name,
                "severity": "warning",
                "message": f"Found {len(matches)} {name.replace('_', ' ')} pattern(s)",
            })

    # Length check
    if total_chars < min_length:
        issues.append({
            "type": "too_short",
            "severity": "critical",
            "message": f"Output is only {total_chars} characters (minimum {min_length})",
        })

    # Paragraph check
    paragraphs = [p for p in content.split("\n\n") if p.strip()]
    if len(paragraphs) < min_paragraphs:
        issues.append({
            "type": "too_few_paragraphs",
            "severity": "warning",
            "message": f"Only {len(paragraphs)} paragraph(s) (minimum {min_paragraphs})",
        })

    # Repetition check — detect copy-paste blocks
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", content) if len(s.strip()) > 20]
    if sentences:
        unique = set(sentences)
        if len(unique) < len(sentences) * 0.7:
            issues.append({
                "type": "repetitive",
                "severity": "warning",
                "message": f"High repetition: {len(sentences)} sentences but only {len(unique)} unique",
            })

    # Compute template ratio
    template_ratio = template_chars / max(1, total_chars)

    # Score: 1.0 = perfect, 0.0 = all placeholders
    critical_count = sum(1 for i in issues if i["severity"] == "critical")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")
    score = max(0.0, 1.0 - (critical_count * 0.25) - (warning_count * 0.05) - template_ratio)
    score = round(min(1.0, score), 3)

    passed = critical_count == 0 and template_ratio <= max_template_ratio

    return {
        "passed": passed,
        "score": score,
        "issues": issues,
        "template_ratio": round(template_ratio, 4),
        "stats": {
            "total_chars": total_chars,
            "paragraphs": len(paragraphs),
            "sentences": len(sentences),
            "unique_sentences": len(set(sentences)) if sentences else 0,
            "critical_issues": critical_count,
            "warnings": warning_count,
        },
    }


def quality_summary(result: dict[str, Any]) -> str:
    """Human-readable one-line quality summary."""
    if result["passed"]:
        return f"Quality OK (score: {result['score']:.0%})"
    issues = result.get("issues", [])
    critical = [i for i in issues if i["severity"] == "critical"]
    if critical:
        return f"Quality FAILED: {critical[0]['message']} (score: {result['score']:.0%})"
    return f"Quality warnings (score: {result['score']:.0%})"
