"""Brain Review Prompts — structured prompts for the Brain reviewer role.

Keeps prompt engineering separate from the review loop logic.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior project manager reviewing your team member's work output.

Your job is to decide if the output is good enough to pass to the next team member, or if it needs improvement.

You must respond with valid JSON only. No markdown, no explanation outside the JSON.

Response format:
{
  "decision": "proceed" | "revise" | "question" | "escalate",
  "reasoning": "brief explanation of your decision",
  "feedback": "specific actionable feedback if decision is revise",
  "question": "specific question if decision is question",
  "confidence": 0.0 to 1.0
}

Decision guide:
- "proceed": Output is good enough. Minor imperfections are OK. Don't be a perfectionist.
- "revise": Output has a real problem — missing data, wrong calculations, placeholder text, contradictions. Give specific feedback on what to fix.
- "question": Output is unclear on a specific point. Ask one focused question.
- "escalate": Output needs verification by a different team member. Rare — only for critical claims.

Be fast. Be specific. Don't revise for style — only for substance."""


def build_review_prompt(
    *,
    agent_id: str,
    step_output: str,
    original_task: str,
    step_description: str = "",
    quality_score: float = 1.0,
) -> dict[str, str]:
    """Build the system + user prompt for the Brain review call."""
    # Truncate output to keep prompt fast
    truncated_output = step_output[:3000] if len(step_output) > 3000 else step_output

    quality_note = ""
    if quality_score < 0.7:
        quality_note = f"\n⚠️ Automated quality check scored this {quality_score:.0%}. Look carefully for issues."

    user_prompt = f"""Review this team member's output.

**Original task:** {original_task[:500]}

**Step assignment:** {step_description[:300]}

**Team member:** {agent_id}
{quality_note}

**Their output:**
{truncated_output}

Respond with JSON only."""

    return {"system": SYSTEM_PROMPT, "user": user_prompt}


def parse_review_response(raw: str) -> dict[str, Any]:
    """Parse the Brain's JSON response into a structured decision."""
    # Try to extract JSON from the response
    text = raw.strip()

    # Handle markdown code blocks
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()

    # Try JSON parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "decision" in parsed:
            return _normalize_decision(parsed)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    for i in range(len(text)):
        if text[i] == "{":
            for j in range(len(text) - 1, i, -1):
                if text[j] == "}":
                    try:
                        parsed = json.loads(text[i : j + 1])
                        if isinstance(parsed, dict) and "decision" in parsed:
                            return _normalize_decision(parsed)
                    except json.JSONDecodeError:
                        continue

    # Fallback: try to infer decision from text
    lower = text.lower()
    if "revise" in lower or "revision" in lower:
        return {"decision": "revise", "reasoning": text[:200], "feedback": text[:500], "question": "", "confidence": 0.5}
    if "question" in lower or "unclear" in lower:
        return {"decision": "question", "reasoning": text[:200], "feedback": "", "question": text[:300], "confidence": 0.5}

    # Default: proceed (don't block the workflow on a parse failure)
    return {"decision": "proceed", "reasoning": "Review completed", "feedback": "", "question": "", "confidence": 0.7}


def _normalize_decision(parsed: dict[str, Any]) -> dict[str, Any]:
    """Ensure all expected fields exist with valid values."""
    decision = str(parsed.get("decision", "proceed")).strip().lower()
    if decision not in ("proceed", "revise", "question", "escalate"):
        decision = "proceed"

    return {
        "decision": decision,
        "reasoning": str(parsed.get("reasoning", ""))[:500],
        "feedback": str(parsed.get("feedback", ""))[:1000],
        "question": str(parsed.get("question", ""))[:500],
        "confidence": min(1.0, max(0.0, float(parsed.get("confidence", 0.7)))),
    }
