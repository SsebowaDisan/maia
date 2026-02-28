from __future__ import annotations

from .models import AnswerBuildContext


def append_execution_plan(lines: list[str], ctx: AnswerBuildContext) -> None:
    lines.append("")
    lines.append("## Execution Plan")
    for idx, step in enumerate(ctx.planned_steps, start=1):
        lines.append(f"{idx}. {step.title} (`{step.tool_id}`)")

    search_terms_raw = ctx.runtime_settings.get("__research_search_terms")
    keywords_raw = ctx.runtime_settings.get("__research_keywords")
    if isinstance(search_terms_raw, list) or isinstance(keywords_raw, list):
        search_terms = (
            [str(item).strip() for item in search_terms_raw if str(item).strip()]
            if isinstance(search_terms_raw, list)
            else []
        )
        keywords = (
            [str(item).strip() for item in keywords_raw if str(item).strip()]
            if isinstance(keywords_raw, list)
            else []
        )
        if search_terms or keywords:
            lines.append("")
            lines.append("## Research Blueprint")
            if search_terms:
                lines.append(f"- Planned search terms: {', '.join(search_terms[:6])}")
            if keywords:
                lines.append(f"- Planned keywords: {', '.join(keywords[:12])}")

    clarification_questions = ctx.runtime_settings.get("__task_clarification_questions")
    if isinstance(clarification_questions, list):
        cleaned_questions = [
            str(item).strip() for item in clarification_questions if str(item).strip()
        ]
        if cleaned_questions:
            lines.append("")
            lines.append("## Clarification Needed")
            for question in cleaned_questions[:6]:
                lines.append(f"- {question}")
