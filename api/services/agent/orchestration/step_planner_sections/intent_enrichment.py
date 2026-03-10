from __future__ import annotations

import os
import re

from api.schemas import ChatRequest
from api.services.agent.planner_helpers import infer_intent_signals_from_text
from api.services.agent.planner import PlannedStep

from ..models import TaskPreparation


DOCS_REQUEST_RE = re.compile(r"\bgoogle\s+docs?\b|\bdocs?\b", re.IGNORECASE)
SHEETS_REQUEST_RE = re.compile(
    r"\bgoogle\s+sheets?\b|\bspreadsheet(?:s)?\b|\bsheets?\b",
    re.IGNORECASE,
)


def _coerce_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    token = " ".join(str(value or "").split()).strip().lower()
    if not token:
        return default
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


def _contact_form_capability_enabled(settings: dict[str, object]) -> bool:
    if "__contact_form_capability_enabled" in settings:
        return _coerce_bool(settings.get("__contact_form_capability_enabled"), default=False)
    return _coerce_bool(
        settings.get("agent.capabilities.contact_form_enabled")
        or settings.get("MAIA_AGENT_CONTACT_FORM_ENABLED")
        or os.getenv("MAIA_AGENT_CONTACT_FORM_ENABLED"),
        default=False,
    )


def _is_research_mode_disallowed_tool(tool_id: str) -> bool:
    normalized = " ".join(str(tool_id or "").split()).strip().lower()
    if not normalized:
        return False
    if normalized in {
        "email.draft",
        "email.send",
        "gmail.draft",
        "gmail.send",
        "invoice.create",
        "invoice.send",
        "slack.post_message",
        "calendar.create_event",
        "browser.contact_form.send",
    }:
        return True
    return normalized.startswith("business.")


def _explicit_workspace_output_flags(
    *,
    request: ChatRequest,
) -> tuple[bool, bool]:
    message_text = " ".join(str(request.message or "").split()).strip()
    # Use explicit terms from the current user message only. Inferred LLM tags
    # are intentionally excluded from this opt-in gate to prevent accidental
    # Docs/Sheets execution when the user did not request workspace output.
    explicit_docs_requested = bool(DOCS_REQUEST_RE.search(message_text))
    explicit_sheets_requested = bool(SHEETS_REQUEST_RE.search(message_text))
    return explicit_docs_requested, explicit_sheets_requested


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
    web_only_mode = _coerce_bool(settings.get("__research_web_only"), default=False)
    research_only_mode = deep_search_mode or web_only_mode
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
    capability_required_domains = {
        " ".join(str(item).split()).strip().lower()
        for item in (
            settings.get("__capability_required_domains")
            if isinstance(settings.get("__capability_required_domains"), list)
            else []
        )
        if " ".join(str(item).split()).strip()
    }
    capability_preferred_tool_ids = {
        " ".join(str(item).split()).strip().lower()
        for item in (
            settings.get("__capability_preferred_tool_ids")
            if isinstance(settings.get("__capability_preferred_tool_ids"), list)
            else []
        )
        if " ".join(str(item).split()).strip()
    }
    target_url = " ".join(
        str(getattr(task_prep.task_intelligence, "target_url", "") or "").split()
    ).strip() or " ".join(str(inferred_signals.get("url") or "").split()).strip()
    contract_or_intent_docs_requested = (
        ("create_document" in contract_actions)
        or ("docs_write" in intent_tags)
        or bool(inferred_signals.get("wants_docs_output"))
    )
    contract_or_intent_sheets_requested = (
        ("update_sheet" in contract_actions)
        or ("sheets_update" in intent_tags)
        or bool(inferred_signals.get("wants_sheets_output"))
    )
    explicit_docs_requested, explicit_sheets_requested = _explicit_workspace_output_flags(
        request=request,
    )
    require_explicit_workspace_request = _coerce_bool(
        settings.get("agent.workspace_logging_require_user_request"),
        default=True,
    )
    if require_explicit_workspace_request:
        docs_requested = explicit_docs_requested
        sheets_requested = explicit_sheets_requested
    else:
        docs_requested = contract_or_intent_docs_requested or explicit_docs_requested
        sheets_requested = contract_or_intent_sheets_requested or explicit_sheets_requested
    if research_only_mode:
        docs_requested = explicit_docs_requested
        sheets_requested = explicit_sheets_requested
    contact_form_requested = (
        ("submit_contact_form" in contract_actions)
        or ("contact_form_submission" in intent_tags)
        or (
            "outreach" in capability_required_domains
            and "browser.contact_form.send" in capability_preferred_tool_ids
        )
    )
    if research_only_mode:
        contact_form_requested = False
    contact_form_enabled = _contact_form_capability_enabled(settings)

    filtered_steps: list[PlannedStep] = []
    for step in steps:
        tool_id = " ".join(str(step.tool_id or "").split()).strip().lower()
        if research_only_mode and _is_research_mode_disallowed_tool(tool_id):
            continue
        # Keep Google Docs/Sheets execution opt-in: only include these tools
        # when the user explicitly requested Docs/Sheets output.
        if not docs_requested and (
            tool_id == "docs.create"
            or tool_id.startswith("workspace.docs.")
        ):
            continue
        if not sheets_requested and tool_id.startswith("workspace.sheets."):
            continue
        filtered_steps.append(step)
    steps = filtered_steps

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
    if contact_form_enabled and contact_form_requested and target_url and not any(
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
