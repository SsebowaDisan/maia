from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.planner_helpers import infer_intent_signals_from_text
from api.services.agent.planner import PlannedStep

from ..models import TaskPreparation


def apply_intent_enrichment(
    *,
    request: ChatRequest,
    task_prep: TaskPreparation,
    steps: list[PlannedStep],
) -> list[PlannedStep]:
    intent_tags = set(task_prep.task_intelligence.intent_tags)
    lexical_signals = infer_intent_signals_from_text(
        message=request.message,
        agent_goal=request.agent_goal,
    )
    highlight_requested = ("highlight_extract" in intent_tags) or bool(
        lexical_signals.get("wants_highlight_words")
    )
    docs_requested = ("docs_write" in intent_tags) or bool(
        lexical_signals.get("wants_docs_output")
    )
    sheets_requested = ("sheets_update" in intent_tags) or bool(
        lexical_signals.get("wants_sheets_output")
    )

    if highlight_requested and not any(
        step.tool_id == "documents.highlight.extract" for step in steps
    ):
        insertion = (
            1 if steps and steps[0].tool_id == "browser.playwright.inspect" else 0
        )
        steps.insert(
            insertion,
            PlannedStep(
                tool_id="documents.highlight.extract",
                title="Highlight words in selected files",
                params={},
            ),
        )
    if docs_requested and not any(
        step.tool_id
        in (
            "docs.create",
            "workspace.docs.research_notes",
            "workspace.docs.fill_template",
        )
        for step in steps
    ):
        steps.append(
            PlannedStep(
                tool_id="workspace.docs.research_notes",
                title="Write findings to Google Docs",
                params={"note": request.message},
            )
        )
    if sheets_requested and not any(
        step.tool_id in ("workspace.sheets.track_step", "workspace.sheets.append")
        for step in steps
    ):
        steps.insert(
            0,
            PlannedStep(
                tool_id="workspace.sheets.track_step",
                title="Track roadmap step in Google Sheets",
                params={
                    "step_name": "Intent-classified roadmap step",
                    "status": "planned",
                    "detail": request.message[:320],
                },
            ),
        )
    return steps
