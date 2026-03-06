from __future__ import annotations

import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool

from .models import AnswerBuildContext
from ..text_helpers import compact

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _requires_simple_explanation(ctx: AnswerBuildContext) -> bool:
    if bool(ctx.runtime_settings.get("__simple_explanation_required")):
        return True
    prefs = ctx.runtime_settings.get("__user_preferences")
    if isinstance(prefs, dict):
        raw = prefs.get("simple_explanation_required")
        if isinstance(raw, bool):
            return raw
        text_raw = str(raw or "").strip().lower()
        if text_raw in {"true", "1", "yes"}:
            return True
        if text_raw in {"false", "0", "no"}:
            return False
    if not env_bool("MAIA_AGENT_LLM_SIMPLE_EXPLANATION_DETECT_ENABLED", default=True):
        return False
    payload = call_json_response(
        system_prompt=(
            "You classify whether a child-friendly simple explanation section is needed. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "simple_explanation_required": false }\n'
            "Rules:\n"
            "- Infer from message, goal, and preferences.\n"
            "- Return false if not clearly requested.\n\n"
            f"Input:\n{ {'message': _clean(ctx.request.message), 'goal': _clean(ctx.request.agent_goal), 'preferences': prefs if isinstance(prefs, dict) else {}} }"
        ),
        temperature=0.0,
        timeout_seconds=8,
        max_tokens=80,
    )
    if not isinstance(payload, dict):
        return False
    raw = payload.get("simple_explanation_required")
    if isinstance(raw, bool):
        return raw
    text_raw = str(raw or "").strip().lower()
    if text_raw in {"true", "1", "yes"}:
        return True
    if text_raw in {"false", "0", "no"}:
        return False
    return False


def _first_sentence(value: str) -> str:
    text = _clean(value)
    if not text:
        return ""
    for delimiter in (". ", "! ", "? "):
        if delimiter in text:
            return text.split(delimiter, 1)[0].strip() + "."
    return text[:220]


def _simple_topic_label(message: str) -> str:
    words = [match.group(0) for match in WORD_RE.finditer(_clean(message))]
    if not words:
        return "this topic"
    return " ".join(words[:6]).strip()


def append_simple_explanation(lines: list[str], ctx: AnswerBuildContext) -> None:
    if not _requires_simple_explanation(ctx):
        return

    report_title = _clean(ctx.runtime_settings.get("__latest_report_title"))
    report_content = _clean(ctx.runtime_settings.get("__latest_report_content"))
    browser_findings = (
        ctx.runtime_settings.get("__latest_browser_findings")
        if isinstance(ctx.runtime_settings.get("__latest_browser_findings"), dict)
        else {}
    )
    browser_excerpt = _first_sentence(_clean(browser_findings.get("excerpt")))
    summary_sentence = ""
    if "### Executive Summary" in report_content:
        after_summary = report_content.split("### Executive Summary", 1)[1]
        summary_sentence = _first_sentence(after_summary)
    if not summary_sentence:
        summary_sentence = browser_excerpt
    topic_label = _simple_topic_label(ctx.request.message)

    lines.append("")
    lines.append("## Simple Explanation (For a 5-Year-Old)")
    lines.append(
        f"- Think of **{topic_label}** like a big storybook: we read many pages, then kept only the true facts."
    )
    if summary_sentence:
        lines.append(f"- What we found: {compact(summary_sentence, 220)}")
    if report_title:
        lines.append(f"- Final report name: {compact(report_title, 120)}.")
    lines.append("- Why this matters: good decisions come from checked facts, not guesses.")
    lines.append("- If anything is unclear, ask me to explain one part with an example.")
