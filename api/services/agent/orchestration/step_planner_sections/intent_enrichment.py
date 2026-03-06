from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.planner_helpers import infer_intent_signals_from_text
from api.services.agent.planner import PlannedStep

from ..models import TaskPreparation


def apply_intent_enrichment(
    *,
    request: ChatRequest,
    settings: dict[str, object],
    task_prep: TaskPreparation,
    steps: list[PlannedStep],
) -> list[PlannedStep]:
    intent_tags = set(task_prep.task_intelligence.intent_tags)
    inferred_signals = infer_intent_signals_from_text(
        message=request.message,
        agent_goal=request.agent_goal,
    )
    deep_search_mode = str(request.agent_mode or "").strip().lower() == "deep_search" or bool(
        settings.get("__deep_search_enabled")
    )
    if deep_search_mode:
        deep_file_scope = bool(settings.get("__deep_search_prompt_scoped_pdfs")) or bool(
            settings.get("__deep_search_user_selected_files")
        ) or any(
            str(getattr(item, "file_id", "") or "").strip()
            for item in (request.attachments if isinstance(request.attachments, list) else [])
        )
        # Deep-search should not auto-scan local files unless file scope is explicit.
        highlight_requested = deep_file_scope
    else:
        highlight_requested = ("highlight_extract" in intent_tags) or bool(
            inferred_signals.get("wants_highlight_words")
        )
    contract_actions = {
        str(action).strip().lower()
        for action in task_prep.contract_actions
        if str(action).strip()
    }
    target_url = " ".join(
        str(getattr(task_prep.task_intelligence, "target_url", "") or "").split()
    ).strip() or " ".join(str(inferred_signals.get("url") or "").split()).strip()
    docs_requested = (
        ("create_document" in contract_actions)
        or ("docs_write" in intent_tags)
        or bool(inferred_signals.get("wants_docs_output"))
    )
    sheets_requested = (
        ("update_sheet" in contract_actions)
        or ("sheets_update" in intent_tags)
        or bool(inferred_signals.get("wants_sheets_output"))
    )
    contact_form_requested = (
        ("submit_contact_form" in contract_actions)
        or ("contact_form_submission" in intent_tags)
        or bool(inferred_signals.get("wants_contact_form"))
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
    if contact_form_requested and target_url and not any(
        step.tool_id == "browser.contact_form.send" for step in steps
    ):
        insertion = len(steps)
        for idx, step in enumerate(steps):
            if step.tool_id == "report.generate":
                insertion = idx
                break
        steps.insert(
            insertion,
            PlannedStep(
                tool_id="browser.contact_form.send",
                title="Fill and submit website contact form",
                params={
                    "url": target_url,
                    "subject": "Business inquiry",
                    "message": request.message,
                },
            ),
        )
    return steps
