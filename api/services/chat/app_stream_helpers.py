from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Generator

from fastapi import HTTPException

from ktem.pages.chat.common import STATE

from api.context import ApiContext
from api.schemas import ChatRequest
from api.services.settings_service import load_user_settings

from .conversation_store import (
    build_selected_payload,
    get_or_create_conversation,
    maybe_autoname_conversation,
)
from .fast_qa import stream_fast_chat_turn
from .app_stream_orchestrator import run_orchestrator_stream_turn
from .app_stream_pipeline import run_pipeline_stream_turn

# Human-readable scope statements emitted as mode_committed events on the first
# turn of a conversation.  Kept as constants so they are fast, deterministic,
# and updatable without LLM access.
_MODE_SCOPE_STATEMENTS: dict[str, str] = {
    "rag": (
        "RAG mode: I will answer from files and indexed URLs already in Maia, "
        "grounding every claim in those sources."
    ),
    "company_agent": (
        "Company Agent mode: I will use your connected tools, "
        "execute multi-step tasks, and cite every action taken."
    ),
    "deep_search": (
        "Deep Search mode: I will query multiple sources, "
        "synthesise evidence, and cite every claim. Expect 30–90 seconds."
    ),
    "brain": (
        "Brain mode: I will assemble a team of agents, build a workflow, "
        "and run it. You will see the agents collaborate in real-time."
    ),
}


def _read_persisted_workspace_ids(chat_state: dict[str, Any]) -> dict[str, str]:
    app_state = chat_state.get("app") if isinstance(chat_state.get("app"), dict) else {}
    return {
        "deep_research_doc_id": str(app_state.get("deep_research_doc_id") or "").strip(),
        "deep_research_doc_url": str(app_state.get("deep_research_doc_url") or "").strip(),
        "deep_research_sheet_id": str(app_state.get("deep_research_sheet_id") or "").strip(),
        "deep_research_sheet_url": str(app_state.get("deep_research_sheet_url") or "").strip(),
    }


def _capture_workspace_ids_from_actions(actions: list[Any]) -> dict[str, str]:
    captured = {
        "deep_research_doc_id": "",
        "deep_research_doc_url": "",
        "deep_research_sheet_id": "",
        "deep_research_sheet_url": "",
    }
    for action in actions or []:
        payload = action.to_dict() if hasattr(action, "to_dict") else action
        if not isinstance(payload, dict):
            continue
        doc_id = str(payload.get("google_doc_id") or "").strip()
        doc_url = str(payload.get("google_doc_url") or "").strip()
        if doc_id and not captured["deep_research_doc_id"]:
            captured["deep_research_doc_id"] = doc_id
        if doc_url and not captured["deep_research_doc_url"]:
            captured["deep_research_doc_url"] = doc_url
        sheet_id = str(payload.get("google_sheet_id") or "").strip()
        sheet_url = str(payload.get("google_sheet_url") or "").strip()
        if sheet_id and not captured["deep_research_sheet_id"]:
            captured["deep_research_sheet_id"] = sheet_id
        if sheet_url and not captured["deep_research_sheet_url"]:
            captured["deep_research_sheet_url"] = sheet_url
    return captured


def _extract_plot_from_actions(actions: list[Any]) -> dict[str, Any] | None:
    def _read_action_field(action: Any, *keys: str) -> Any:
        if isinstance(action, dict):
            for key in keys:
                value = action.get(key)
                if value is not None:
                    return value
            return None
        for key in keys:
            value = getattr(action, key, None)
            if value is not None:
                return value
        return None

    for action in reversed(actions or []):
        tool_name = _read_action_field(action, "tool", "tool_id")
        if str(tool_name or "").strip() != "python_exec":
            continue
        output = _read_action_field(action, "output")
        payload = output if isinstance(output, dict) else {}
        plot = payload.get("plot")
        if isinstance(plot, dict):
            return plot
    return None


def stream_chat_turn(
    *,
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
    auto_index_urls_for_request_fn: Callable[..., ChatRequest],
    apply_deep_search_defaults_fn: Callable[..., ChatRequest],
    normalize_request_attachments_fn: Callable[[ChatRequest], list[dict[str, str]]],
    mode_variant_from_request_fn: Callable[..., str],
    is_orchestrator_mode_fn: Callable[[str], bool],
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")

    settings = load_user_settings(context, user_id)
    request = auto_index_urls_for_request_fn(
        context=context,
        user_id=user_id,
        request=request,
        settings=settings,
    )
    request = apply_deep_search_defaults_fn(
        context=context,
        user_id=user_id,
        request=request,
    )
    message = request.message.strip()
    conversation_id, conversation_name, data_source, conversation_icon_key = get_or_create_conversation(
        user_id=user_id,
        conversation_id=request.conversation_id,
    )
    conversation_name, conversation_icon_key = maybe_autoname_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        current_name=conversation_name,
        message=message,
        agent_mode=request.agent_mode,
    )
    data_source = deepcopy(data_source or {})
    data_source["conversation_icon_key"] = conversation_icon_key

    chat_history = deepcopy(data_source.get("messages", []))
    chat_state = deepcopy(data_source.get("state", STATE))
    persisted_workspace_ids = _read_persisted_workspace_ids(chat_state)
    selected_payload = build_selected_payload(
        context=context,
        user_id=user_id,
        existing_selected=data_source.get("selected", {}),
        requested_selected=request.index_selection,
    )
    turn_attachments = normalize_request_attachments_fn(request)

    requested_mode = str(request.agent_mode or "").strip().lower() or "ask"
    mode_variant = mode_variant_from_request_fn(request=request, requested_mode=requested_mode)
    committed_mode = mode_variant or requested_mode
    if not chat_history and committed_mode in _MODE_SCOPE_STATEMENTS:
        yield {
            "type": "mode_committed",
            "mode": committed_mode,
            "scope_statement": _MODE_SCOPE_STATEMENTS[committed_mode],
        }

    if is_orchestrator_mode_fn(requested_mode):
        return (
            yield from run_orchestrator_stream_turn(
                request=request,
                user_id=user_id,
                message=message,
                settings=settings,
                conversation_id=conversation_id,
                conversation_name=conversation_name,
                data_source=data_source,
                chat_history=chat_history,
                chat_state=chat_state,
                persisted_workspace_ids=persisted_workspace_ids,
                selected_payload=selected_payload,
                turn_attachments=turn_attachments,
                requested_mode=requested_mode,
                mode_variant=mode_variant,
                capture_workspace_ids_from_actions_fn=_capture_workspace_ids_from_actions,
                extract_plot_from_actions_fn=_extract_plot_from_actions,
            )
        )

    if committed_mode == "rag":
        return (
            yield from stream_fast_chat_turn(
                context=context,
                user_id=user_id,
                request=request,
            )
        )

    return (
        yield from run_pipeline_stream_turn(
            context=context,
            user_id=user_id,
            request=request,
            settings=settings,
            chat_state=chat_state,
            selected_payload=selected_payload,
            message=message,
            conversation_id=conversation_id,
            conversation_name=conversation_name,
            chat_history=chat_history,
            data_source=data_source,
            turn_attachments=turn_attachments,
            requested_mode=requested_mode,
            mode_variant=mode_variant,
        )
    )
