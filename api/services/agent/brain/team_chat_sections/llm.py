from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_CHAT_TURNS = 16

PERSONALITY_PROMPT = """You are {name}, a {role} on the team.

Your personality:
- Communication style: {style}
- When you agree: {agree_style}
- When you disagree: {disagree_style}
- Your quirk: {quirk}

Rules for this conversation:
1. Keep messages SHORT - 1-3 sentences max. This is chat, not email.
2. Think out loud - say "Hmm..." or "Let me check..." before big claims.
3. Use specific numbers and examples, not vague generalisations.
4. If you disagree, say so directly but respectfully.
5. If something surprises you, show it - "Wait, really?" or "That's unexpected."
6. Reference what teammates said - "@name good point about X, but..."
7. Don't repeat what others already said. Build on it or challenge it.
8. Do not open with filler or generic acknowledgements. Lead with the next concrete move, risk, evidence, or question.
"""

PERSONALITY_ARCHETYPES = [
    {
        "style": "Direct and data-driven. You lead with numbers.",
        "agree_style": "You nod and add a supporting data point.",
        "disagree_style": "You say 'The data tells a different story' and show evidence.",
        "quirk": "You always quantify things - 'that's roughly a 23% improvement'.",
    },
    {
        "style": "Curious and questioning. You ask 'why' a lot.",
        "agree_style": "You agree but immediately ask a follow-up question.",
        "disagree_style": "You ask 'Have we considered...' and propose alternatives.",
        "quirk": "You spot edge cases others miss.",
    },
    {
        "style": "Concise and action-oriented. You cut to what matters.",
        "agree_style": "You say 'Agreed' and immediately suggest next steps.",
        "disagree_style": "You say 'That won't work because...' with a concrete reason.",
        "quirk": "You always end with a clear action item.",
    },
    {
        "style": "Thoughtful and thorough. You consider multiple angles.",
        "agree_style": "You agree and add context others might have missed.",
        "disagree_style": "You say 'I see it differently' and explain your reasoning.",
        "quirk": "You draw connections between unrelated findings.",
    },
    {
        "style": "Enthusiastic and creative. You get excited about possibilities.",
        "agree_style": "You build on the idea with a creative extension.",
        "disagree_style": "You say 'What if we tried it this way instead' with an alternative.",
        "quirk": "You use analogies to explain complex things.",
    },
    {
        "style": "Skeptical and rigorous. You stress-test everything.",
        "agree_style": "You say 'That checks out' only after verifying.",
        "disagree_style": "You say 'Hold on, that assumption doesn't hold because...'",
        "quirk": "You always ask 'What could go wrong?'",
    },
]


def _get_personality(agent_idx: int) -> dict[str, str]:
    return PERSONALITY_ARCHETYPES[agent_idx % len(PERSONALITY_ARCHETYPES)]


def _call_agent_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    tenant_id: str = "",
    max_tokens: int = 200,
) -> str:
    try:
        from api.services.agent.llm_runtime import call_text_response

        return call_text_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=30,
            max_tokens=max_tokens,
            retries=1,
            enable_thinking=False,
        )
    except Exception:
        pass
    try:
        from api.services.agents.runner import run_agent_task

        parts: list[str] = []
        for chunk in run_agent_task(
            user_prompt,
            tenant_id=tenant_id,
            system_prompt=system_prompt,
            agent_mode="ask",
            max_tool_calls=0,
        ):
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                parts.append(str(text))
        return "".join(parts)
    except Exception as exc:
        logger.warning("Agent LLM call failed: %s", exc)
        return ""


def _call_json_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    tenant_id: str = "",
) -> dict[str, Any]:
    try:
        from api.services.agent.llm_runtime import call_json_response

        result = call_json_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=30,
            max_tokens=300,
            retries=1,
            allow_json_repair=True,
            enable_thinking=False,
        )
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    text = _call_agent_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tenant_id=tenant_id,
    )
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {}


def _infer_mood_from_response(text: str) -> str:
    """Let the LLM classify the mood - no hardcoded patterns."""
    try:
        result = _call_json_llm(
            system_prompt="Classify the mood of this message in ONE word.",
            user_prompt=(
                f"Message: {text[:300]}\n\n"
                "Pick exactly ONE mood: neutral, curious, confident, skeptical, excited, concerned\n\n"
                'JSON: {"mood": "word"}'
            ),
            tenant_id="",
        )
        mood = str(result.get("mood", "neutral")).strip().lower()
        if mood in (
            "neutral",
            "curious",
            "confident",
            "skeptical",
            "excited",
            "concerned",
        ):
            return mood
    except Exception:
        pass
    return "neutral"
