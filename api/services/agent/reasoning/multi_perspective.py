"""Multi-Perspective Debate — generates analysis from 3 distinct LLM personas.

Inspired by AutoResearchClaw's hypothesis generation pattern.
Instead of one LLM call, three personas generate independently,
then a synthesis prompt merges them into a stronger result.

Usage:
    result = await run_multi_perspective_debate(
        topic="Q3 revenue decline analysis",
        context="Revenue dropped 12% QoQ...",
        llm_call=my_llm_function,
    )
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# ── Persona definitions ───────────────────────────────────────────────────────

ANALYSIS_PERSONAS: list[dict[str, str]] = [
    {
        "name": "Optimist",
        "system": (
            "You are an optimistic analyst. You focus on opportunities, positive trends, "
            "and strengths. Look for silver linings, growth signals, and what's working well. "
            "Support your points with specific data from the context provided."
        ),
    },
    {
        "name": "Skeptic",
        "system": (
            "You are a skeptical analyst. You focus on risks, weaknesses, and what could go wrong. "
            "Challenge assumptions, look for hidden problems, and flag anything that seems too good "
            "to be true. Support your points with specific data from the context provided."
        ),
    },
    {
        "name": "Methodologist",
        "system": (
            "You are a methodical analyst. You focus on process, data quality, and rigour. "
            "Check whether conclusions follow from the data, flag gaps in the analysis, "
            "and suggest what additional data would strengthen the findings. "
            "Support your points with specific data from the context provided."
        ),
    },
]

RESEARCH_PERSONAS: list[dict[str, str]] = [
    {
        "name": "Innovator",
        "system": (
            "You are a creative researcher. Propose novel angles, unexpected connections, "
            "and unconventional approaches. Think laterally — what has everyone else missed?"
        ),
    },
    {
        "name": "Pragmatist",
        "system": (
            "You are a practical researcher. Focus on what's feasible, actionable, and proven. "
            "Ground ideas in real-world constraints and existing evidence."
        ),
    },
    {
        "name": "Contrarian",
        "system": (
            "You are a contrarian researcher. Challenge the premise, question popular assumptions, "
            "and explore the opposite of what seems obvious. Play devil's advocate constructively."
        ),
    },
]

SYNTHESIS_PROMPT = """You received three independent analyses of the same topic from different perspectives.

**Optimist/Innovator perspective:**
{perspective_1}

**Skeptic/Pragmatist perspective:**
{perspective_2}

**Methodologist/Contrarian perspective:**
{perspective_3}

Synthesize these into a single, balanced analysis that:
1. Captures the strongest points from each perspective
2. Resolves contradictions by weighing evidence
3. Flags genuine uncertainties where perspectives disagree
4. Produces actionable conclusions

Write the synthesis directly — do not reference the personas."""

# Type for the LLM call function
LLMCall = Callable[[str, str], Awaitable[str]]


async def run_multi_perspective_debate(
    *,
    topic: str,
    context: str,
    llm_call: LLMCall,
    persona_set: str = "analysis",
    max_tokens_per_perspective: int = 800,
) -> dict[str, Any]:
    """Run three LLM personas on the same topic, then synthesize.

    Args:
        topic: The question or topic to analyse.
        context: Supporting data/text for the analysis.
        llm_call: async function(system_prompt, user_prompt) -> str
        persona_set: "analysis" or "research"

    Returns:
        dict with keys: synthesis, perspectives (list of 3), persona_set
    """
    personas = ANALYSIS_PERSONAS if persona_set == "analysis" else RESEARCH_PERSONAS

    user_prompt = f"Topic: {topic}\n\nContext:\n{context}\n\nProvide your analysis."

    # Generate all three perspectives
    perspectives: list[dict[str, str]] = []
    for persona in personas:
        try:
            response = await llm_call(persona["system"], user_prompt)
            perspectives.append({"name": persona["name"], "content": response})
        except Exception as exc:
            logger.warning("Perspective '%s' failed: %s", persona["name"], exc)
            perspectives.append({"name": persona["name"], "content": f"[Failed: {exc}]"})

    if not any(p["content"] and not p["content"].startswith("[Failed") for p in perspectives):
        return {"synthesis": "", "perspectives": perspectives, "persona_set": persona_set, "error": "All perspectives failed"}

    # Synthesize
    synthesis_user = SYNTHESIS_PROMPT.format(
        perspective_1=perspectives[0]["content"],
        perspective_2=perspectives[1]["content"],
        perspective_3=perspectives[2]["content"] if len(perspectives) > 2 else "",
    )
    try:
        synthesis = await llm_call(
            "You are a senior analyst producing a balanced synthesis of multiple perspectives.",
            synthesis_user,
        )
    except Exception as exc:
        logger.warning("Synthesis failed: %s", exc)
        synthesis = perspectives[0]["content"]

    return {
        "synthesis": synthesis,
        "perspectives": perspectives,
        "persona_set": persona_set,
    }


def run_multi_perspective_debate_sync(
    *,
    topic: str,
    context: str,
    llm_call_sync: Callable[[str, str], str],
    persona_set: str = "analysis",
) -> dict[str, Any]:
    """Synchronous version for non-async contexts."""
    personas = ANALYSIS_PERSONAS if persona_set == "analysis" else RESEARCH_PERSONAS
    user_prompt = f"Topic: {topic}\n\nContext:\n{context}\n\nProvide your analysis."

    perspectives: list[dict[str, str]] = []
    for persona in personas:
        try:
            response = llm_call_sync(persona["system"], user_prompt)
            perspectives.append({"name": persona["name"], "content": response})
        except Exception as exc:
            perspectives.append({"name": persona["name"], "content": f"[Failed: {exc}]"})

    synthesis_user = SYNTHESIS_PROMPT.format(
        perspective_1=perspectives[0]["content"],
        perspective_2=perspectives[1]["content"] if len(perspectives) > 1 else "",
        perspective_3=perspectives[2]["content"] if len(perspectives) > 2 else "",
    )
    try:
        synthesis = llm_call_sync(
            "You are a senior analyst producing a balanced synthesis of multiple perspectives.",
            synthesis_user,
        )
    except Exception:
        synthesis = perspectives[0]["content"] if perspectives else ""

    return {"synthesis": synthesis, "perspectives": perspectives, "persona_set": persona_set}
