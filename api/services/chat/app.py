from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from copy import deepcopy
from datetime import datetime
from typing import Any, Generator

from fastapi import HTTPException
from theflow.settings import settings as flowsettings
from tzlocal import get_localzone

from maia.base import Document

from ktem.pages.chat.common import STATE
from ktem.llms.manager import llms

from api.context import ApiContext
from api.schemas import ChatRequest
from api.services.agent.orchestrator import get_orchestrator
from api.services.settings_service import load_user_settings

from .constants import API_CHAT_FAST_PATH, logger
from .citations import append_required_citation_suffix, enforce_required_citations
from .conversation_store import (
    build_selected_payload,
    get_or_create_conversation,
    maybe_autoname_conversation,
    persist_conversation,
)
from .fallbacks import build_extractive_timeout_answer, fallback_answer_from_exception
from .fast_qa import run_fast_chat_turn
from .info_panel_copy import build_info_panel_copy
from .pipeline import create_pipeline
from .streaming import (
    build_agent_context_window,
    chunk_text_for_stream,
    make_activity_stream_event,
)


def _default_model_looks_local_ollama() -> bool:
    try:
        default_name = str(llms.get_default_name() or "").strip()
    except Exception:
        return False
    if default_name.startswith("ollama::"):
        return True
    try:
        info = llms.info().get(default_name, {})
    except Exception:
        return False
    spec = info.get("spec", {}) if isinstance(info, dict) else {}
    if not isinstance(spec, dict):
        return False
    return str(spec.get("api_key") or "").strip().lower() == "ollama"


def _read_persisted_workspace_ids(chat_state: dict[str, Any]) -> dict[str, str]:
    app_state = chat_state.get("app") if isinstance(chat_state, dict) else None
    app_rows = app_state if isinstance(app_state, dict) else {}
    return {
        "deep_research_doc_id": str(app_rows.get("deep_research_doc_id") or "").strip(),
        "deep_research_doc_url": str(app_rows.get("deep_research_doc_url") or "").strip(),
        "deep_research_sheet_id": str(app_rows.get("deep_research_sheet_id") or "").strip(),
        "deep_research_sheet_url": str(app_rows.get("deep_research_sheet_url") or "").strip(),
    }


def _capture_workspace_ids_from_actions(actions: list[Any]) -> dict[str, str]:
    captured = {
        "deep_research_doc_id": "",
        "deep_research_doc_url": "",
        "deep_research_sheet_id": "",
        "deep_research_sheet_url": "",
    }
    for action in reversed(actions or []):
        tool_id = str(getattr(action, "tool_id", "") or "").strip()
        status = str(getattr(action, "status", "") or "").strip().lower()
        if status != "success":
            continue
        metadata = getattr(action, "metadata", {})
        meta = metadata if isinstance(metadata, dict) else {}
        if not captured["deep_research_doc_id"] and tool_id == "workspace.docs.research_notes":
            captured["deep_research_doc_id"] = str(meta.get("document_id") or "").strip()
            captured["deep_research_doc_url"] = str(meta.get("document_url") or "").strip()
        if not captured["deep_research_sheet_id"] and tool_id in (
            "workspace.sheets.track_step",
            "workspace.sheets.append",
        ):
            captured["deep_research_sheet_id"] = str(meta.get("spreadsheet_id") or "").strip()
            captured["deep_research_sheet_url"] = str(meta.get("spreadsheet_url") or "").strip()
        if all(captured.values()):
            break
    return captured


def _extract_plot_from_actions(actions: list[Any]) -> dict[str, Any] | None:
    for action in reversed(actions or []):
        status = str(getattr(action, "status", "") or "").strip().lower()
        if status and status != "success":
            continue
        metadata = getattr(action, "metadata", {})
        if not isinstance(metadata, dict):
            continue
        plot = metadata.get("plot")
        if isinstance(plot, dict) and str(plot.get("kind") or "").strip().lower() == "chart":
            return dict(plot)
    return None


def stream_chat_turn(
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")

    settings = load_user_settings(context, user_id)
    conversation_id, conversation_name, data_source = get_or_create_conversation(
        user_id=user_id,
        conversation_id=request.conversation_id,
    )
    conversation_name = maybe_autoname_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        current_name=conversation_name,
        message=message,
        agent_mode=request.agent_mode,
    )

    chat_history = deepcopy(data_source.get("messages", []))
    chat_state = deepcopy(data_source.get("state", STATE))
    persisted_workspace_ids = _read_persisted_workspace_ids(chat_state)
    selected_payload = build_selected_payload(
        context=context,
        user_id=user_id,
        existing_selected=data_source.get("selected", {}),
        requested_selected=request.index_selection,
    )

    if request.agent_mode == "company_agent":
        orchestrator = get_orchestrator()
        agent_result = None
        last_activity_seq = 0
        context_snippets, context_summary = build_agent_context_window(
            chat_history=chat_history,
            latest_message=message,
            agent_goal=request.agent_goal,
        )
        agent_goal_parts = []
        existing_goal = " ".join(str(request.agent_goal or "").split()).strip()
        if existing_goal:
            agent_goal_parts.append(existing_goal)
        if context_summary:
            agent_goal_parts.append(f"Conversation context: {context_summary}")
        contextual_goal = " ".join(agent_goal_parts).strip()[:900]
        agent_request = request
        if contextual_goal and contextual_goal != existing_goal:
            try:
                agent_request = request.model_copy(update={"agent_goal": contextual_goal})
            except Exception:
                request_payload = request.model_dump()
                request_payload["agent_goal"] = contextual_goal
                agent_request = ChatRequest(**request_payload)
        agent_settings = dict(settings)
        if context_snippets:
            agent_settings["__conversation_snippets"] = context_snippets
        if context_summary:
            agent_settings["__conversation_summary"] = context_summary
        agent_settings["__conversation_latest_user_message"] = message
        if persisted_workspace_ids["deep_research_doc_id"]:
            agent_settings["__deep_research_doc_id"] = persisted_workspace_ids["deep_research_doc_id"]
        if persisted_workspace_ids["deep_research_doc_url"]:
            agent_settings["__deep_research_doc_url"] = persisted_workspace_ids["deep_research_doc_url"]
        if persisted_workspace_ids["deep_research_sheet_id"]:
            agent_settings["__deep_research_sheet_id"] = persisted_workspace_ids["deep_research_sheet_id"]
        if persisted_workspace_ids["deep_research_sheet_url"]:
            agent_settings["__deep_research_sheet_url"] = persisted_workspace_ids["deep_research_sheet_url"]
            agent_settings["__deep_research_sheet_header_written"] = True
        try:
            iterator = orchestrator.run_stream(
                user_id=user_id,
                conversation_id=conversation_id,
                request=agent_request,
                settings=agent_settings,
            )
            while True:
                event = next(iterator)
                if isinstance(event, dict):
                    if event.get("type") == "activity":
                        payload = event.get("event")
                        if isinstance(payload, dict):
                            seq_raw = payload.get("seq")
                            if isinstance(seq_raw, int):
                                last_activity_seq = max(last_activity_seq, seq_raw)
                            elif isinstance(seq_raw, str) and seq_raw.isdigit():
                                last_activity_seq = max(last_activity_seq, int(seq_raw))
                    yield event
        except StopIteration as stop:
            agent_result = stop.value
        except Exception as exc:
            logger.exception("Company agent execution failed: %s", exc)
            fallback = fallback_answer_from_exception(exc)
            agent_result = type(
                "_FallbackAgentResult",
                (),
                {
                    "run_id": "",
                    "answer": fallback,
                    "info_html": "",
                    "actions_taken": [],
                    "sources_used": [],
                    "next_recommended_steps": [],
                    "needs_human_review": False,
                    "human_review_notes": "",
                    "web_summary": {},
                },
            )()

        run_id_value = str(getattr(agent_result, "run_id", "") or "")
        if run_id_value:
            last_activity_seq += 1
            yield {
                "type": "activity",
                "event": make_activity_stream_event(
                    run_id=run_id_value,
                    event_type="response_writing",
                    title="Writing final response",
                    detail="Composing grounded answer from executed tool outputs",
                    seq=last_activity_seq,
                ),
            }

        answer_text = ""
        for delta in chunk_text_for_stream(agent_result.answer):
            answer_text += delta
            yield {
                "type": "chat_delta",
                "delta": delta,
                "text": answer_text,
            }

        if run_id_value:
            last_activity_seq += 1
            yield {
                "type": "activity",
                "event": make_activity_stream_event(
                    run_id=run_id_value,
                    event_type="response_written",
                    title="Response draft completed",
                    detail=f"Prepared {len(answer_text)} characters for delivery",
                    seq=last_activity_seq,
                ),
            }
        if agent_result.info_html:
            yield {"type": "info_delta", "delta": agent_result.info_html}
        answer_text = enforce_required_citations(
            answer=answer_text,
            info_html=str(getattr(agent_result, "info_html", "") or ""),
            citation_mode=request.citation,
        )
        plot_data = _extract_plot_from_actions(agent_result.actions_taken)
        if plot_data:
            yield {"type": "plot", "plot": plot_data}
        agent_web_summary = (
            dict(getattr(agent_result, "web_summary", {}))
            if isinstance(getattr(agent_result, "web_summary", {}), dict)
            else {}
        )
        mindmap_payload: dict[str, Any] = {}
        info_panel = build_info_panel_copy(
            request_message=message,
            answer_text=answer_text,
            info_html=str(getattr(agent_result, "info_html", "") or ""),
            mode="company_agent",
            next_steps=list(getattr(agent_result, "next_recommended_steps", []) or []),
            web_summary=agent_web_summary,
        )
        if mindmap_payload:
            info_panel["mindmap"] = mindmap_payload

        chat_state.setdefault("app", {})
        chat_state["app"]["last_agent_run_id"] = agent_result.run_id
        captured_workspace_ids = _capture_workspace_ids_from_actions(agent_result.actions_taken)
        if captured_workspace_ids["deep_research_doc_id"]:
            chat_state["app"]["deep_research_doc_id"] = captured_workspace_ids["deep_research_doc_id"]
        if captured_workspace_ids["deep_research_doc_url"]:
            chat_state["app"]["deep_research_doc_url"] = captured_workspace_ids["deep_research_doc_url"]
        if captured_workspace_ids["deep_research_sheet_id"]:
            chat_state["app"]["deep_research_sheet_id"] = captured_workspace_ids["deep_research_sheet_id"]
        if captured_workspace_ids["deep_research_sheet_url"]:
            chat_state["app"]["deep_research_sheet_url"] = captured_workspace_ids["deep_research_sheet_url"]

        messages = chat_history + [[message, answer_text]]
        retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
        retrieval_history.append(agent_result.info_html)
        plot_history = deepcopy(data_source.get("plot_history", []))
        plot_history.append(plot_data)
        message_meta = deepcopy(data_source.get("message_meta", []))
        message_meta.append(
            {
                "mode": "company_agent",
                "activity_run_id": agent_result.run_id or None,
                "actions_taken": [item.to_dict() for item in agent_result.actions_taken],
                "sources_used": [item.to_dict() for item in agent_result.sources_used],
                "source_usage": [],
                "next_recommended_steps": agent_result.next_recommended_steps,
                "needs_human_review": bool(getattr(agent_result, "needs_human_review", False)),
                "human_review_notes": str(getattr(agent_result, "human_review_notes", "") or "").strip() or None,
                "web_summary": agent_web_summary,
                "info_panel": info_panel,
                "mindmap": mindmap_payload,
            }
        )

        agent_runs = deepcopy(data_source.get("agent_runs", []))
        agent_runs.append(
            {
                "run_id": agent_result.run_id,
                "mode": request.agent_mode,
                "actions_taken": [item.to_dict() for item in agent_result.actions_taken],
                "sources_used": [item.to_dict() for item in agent_result.sources_used],
                "source_usage": [],
                "next_recommended_steps": agent_result.next_recommended_steps,
                "needs_human_review": bool(getattr(agent_result, "needs_human_review", False)),
                "human_review_notes": str(getattr(agent_result, "human_review_notes", "") or "").strip() or None,
                "web_summary": agent_web_summary,
                "date_created": datetime.now(get_localzone()).isoformat(),
            }
        )

        conversation_payload = {
            "selected": selected_payload,
            "messages": messages,
            "retrieval_messages": retrieval_history,
            "plot_history": plot_history,
            "message_meta": message_meta,
            "state": chat_state,
            "likes": deepcopy(data_source.get("likes", [])),
            "agent_runs": agent_runs,
        }
        persist_conversation(conversation_id, conversation_payload)

        return {
            "conversation_id": conversation_id,
            "conversation_name": conversation_name,
            "message": message,
            "answer": answer_text,
            "info": agent_result.info_html,
            "plot": plot_data,
            "state": chat_state,
            "mode": "company_agent",
            "actions_taken": [item.to_dict() for item in agent_result.actions_taken],
            "sources_used": [item.to_dict() for item in agent_result.sources_used],
            "source_usage": [],
            "next_recommended_steps": agent_result.next_recommended_steps,
            "needs_human_review": bool(getattr(agent_result, "needs_human_review", False)),
            "human_review_notes": str(getattr(agent_result, "human_review_notes", "") or "").strip() or None,
            "web_summary": agent_web_summary,
            "activity_run_id": agent_result.run_id,
            "info_panel": info_panel,
            "mindmap": mindmap_payload,
        }

    pipeline, reasoning_state, reasoning_id = create_pipeline(
        context=context,
        settings=settings,
        request=request,
        user_id=user_id,
        state=chat_state,
        selected_by_index=selected_payload,
    )

    answer_text = ""
    info_text = ""
    plot_data: dict[str, Any] | None = None
    mindmap_payload: dict[str, Any] = {}

    pipeline_error: Exception | None = None
    mindmap_settings = dict(request.mindmap_settings or {})
    try:
        requested_mindmap_depth = int(mindmap_settings.get("max_depth", 4))
    except Exception:
        requested_mindmap_depth = 4
    requested_map_type = str(mindmap_settings.get("map_type", "structure") or "structure").strip().lower()
    if requested_map_type not in {"structure", "evidence"}:
        requested_map_type = "structure"
    try:
        for response in pipeline.stream(
            message,
            conversation_id,
            chat_history,
            mindmap_focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
            mindmap_max_depth=max(2, min(8, requested_mindmap_depth)),
            include_reasoning_map=bool(mindmap_settings.get("include_reasoning_map", True)),
            mindmap_map_type=requested_map_type,
        ):
            if not isinstance(response, Document) or response.channel is None:
                continue

            if response.channel == "chat":
                delta = response.content if response.content else ""
                if delta:
                    answer_text += delta
                    yield {
                        "type": "chat_delta",
                        "delta": delta,
                        "text": answer_text,
                    }

            elif response.channel == "info":
                if isinstance(getattr(response, "metadata", None), dict):
                    parsed_mindmap = response.metadata.get("mindmap")
                    if isinstance(parsed_mindmap, dict) and not mindmap_payload:
                        mindmap_payload = parsed_mindmap
                        yield {"type": "mindmap", "mindmap": mindmap_payload}
                delta = response.content if response.content else ""
                if delta:
                    info_text += delta
                    yield {
                        "type": "info_delta",
                        "delta": delta,
                    }

            elif response.channel == "plot":
                plot_data = response.content
                yield {"type": "plot", "plot": plot_data}

            elif response.channel == "debug":
                text = response.text if response.text else str(response.content)
                if text:
                    yield {"type": "debug", "message": text}
    except HTTPException as exc:
        logger.exception("Chat pipeline raised HTTPException: %s", exc)
        pipeline_error = exc
    except Exception as exc:
        logger.exception("Chat pipeline raised Exception: %s", exc)
        pipeline_error = exc

    if pipeline_error is not None and not answer_text:
        answer_text = fallback_answer_from_exception(pipeline_error)
        yield {"type": "chat_delta", "delta": answer_text, "text": answer_text}

    if not answer_text:
        answer_text = getattr(
            flowsettings,
            "KH_CHAT_EMPTY_MSG_PLACEHOLDER",
            "(Sorry, I don't know)",
        )
        yield {"type": "chat_delta", "delta": answer_text, "text": answer_text}

    answer_with_citation_suffix = append_required_citation_suffix(answer=answer_text, info_html=info_text)
    if answer_with_citation_suffix != answer_text:
        if answer_with_citation_suffix.startswith(answer_text):
            delta = answer_with_citation_suffix[len(answer_text) :]
            answer_text = answer_with_citation_suffix
            if delta:
                yield {"type": "chat_delta", "delta": delta, "text": answer_text}
        else:
            answer_text = answer_with_citation_suffix
            yield {"type": "chat_delta", "delta": f"\n\n{answer_text}", "text": answer_text}
    info_panel = build_info_panel_copy(
        request_message=message,
        answer_text=answer_text,
        info_html=info_text,
        mode="ask",
        next_steps=[],
        web_summary={},
    )
    if mindmap_payload:
        info_panel["mindmap"] = mindmap_payload

    chat_state.setdefault("app", {})
    chat_state["app"].update(reasoning_state.get("app", {}))
    chat_state[reasoning_id] = reasoning_state.get("pipeline", {})

    messages = chat_history + [[message, answer_text]]
    retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
    retrieval_history.append(info_text)
    plot_history = deepcopy(data_source.get("plot_history", []))
    plot_history.append(plot_data)
    message_meta = deepcopy(data_source.get("message_meta", []))
    message_meta.append(
        {
            "mode": "ask",
            "activity_run_id": None,
            "actions_taken": [],
            "sources_used": [],
            "source_usage": [],
            "next_recommended_steps": [],
            "needs_human_review": False,
            "human_review_notes": None,
            "web_summary": {},
            "info_panel": info_panel,
            "mindmap": mindmap_payload,
        }
    )

    conversation_payload = {
        "selected": selected_payload,
        "messages": messages,
        "retrieval_messages": retrieval_history,
        "plot_history": plot_history,
        "message_meta": message_meta,
        "state": chat_state,
        "likes": deepcopy(data_source.get("likes", [])),
    }
    persist_conversation(conversation_id, conversation_payload)

    return {
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "message": message,
        "answer": answer_text,
        "info": info_text,
        "plot": plot_data,
        "state": chat_state,
        "mode": "ask",
        "actions_taken": [],
        "sources_used": [],
        "source_usage": [],
        "next_recommended_steps": [],
        "needs_human_review": False,
        "human_review_notes": None,
        "web_summary": {},
        "activity_run_id": None,
        "info_panel": info_panel,
        "mindmap": mindmap_payload,
    }


def run_chat_turn(context: ApiContext, user_id: str, request: ChatRequest) -> dict[str, Any]:
    if API_CHAT_FAST_PATH and request.agent_mode != "company_agent":
        try:
            fast_result = run_fast_chat_turn(context=context, user_id=user_id, request=request)
            if fast_result is not None:
                return fast_result
        except Exception as exc:
            logger.exception("Fast ask path failed; falling back to streaming pipeline: %s", exc)

    timeout_seconds = int(getattr(flowsettings, "KH_CHAT_TIMEOUT_SECONDS", 45) or 45)
    if _default_model_looks_local_ollama():
        local_timeout = int(
            getattr(flowsettings, "KH_CHAT_TIMEOUT_SECONDS_LOCAL_OLLAMA", 180) or 180
        )
        timeout_seconds = max(timeout_seconds, local_timeout)

    def consume_stream() -> dict[str, Any]:
        iterator = stream_chat_turn(context=context, user_id=user_id, request=request)
        try:
            while True:
                next(iterator)
        except StopIteration as stop:
            return stop.value

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(consume_stream)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        message = request.message.strip()
        conversation_id, conversation_name, data_source = get_or_create_conversation(
            user_id=user_id,
            conversation_id=request.conversation_id,
        )
        conversation_name = maybe_autoname_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            current_name=conversation_name,
            message=message,
            agent_mode=request.agent_mode,
        )
        timeout_answer, timeout_info = build_extractive_timeout_answer(
            context=context,
            user_id=user_id,
        )
        timeout_answer = enforce_required_citations(
            answer=timeout_answer,
            info_html=timeout_info,
            citation_mode=request.citation,
        )
        timeout_info_panel = build_info_panel_copy(
            request_message=message,
            answer_text=timeout_answer,
            info_html=timeout_info,
            mode="ask",
            next_steps=[],
            web_summary={},
        )

        messages = deepcopy(data_source.get("messages", []))
        if message:
            messages.append([message, timeout_answer])
        retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
        retrieval_history.append(timeout_info)
        plot_history = deepcopy(data_source.get("plot_history", []))
        plot_history.append(None)
        message_meta = deepcopy(data_source.get("message_meta", []))
        message_meta.append(
            {
                "mode": "ask",
                "activity_run_id": None,
                "actions_taken": [],
                "sources_used": [],
                "source_usage": [],
                "next_recommended_steps": [],
                "needs_human_review": False,
                "human_review_notes": None,
                "web_summary": {},
                "info_panel": timeout_info_panel,
                "mindmap": {},
            }
        )

        conversation_payload = {
            "selected": deepcopy(data_source.get("selected", {})),
            "messages": messages,
            "retrieval_messages": retrieval_history,
            "plot_history": plot_history,
            "message_meta": message_meta,
            "state": deepcopy(data_source.get("state", STATE)),
            "likes": deepcopy(data_source.get("likes", [])),
        }
        persist_conversation(conversation_id, conversation_payload)

        return {
            "conversation_id": conversation_id,
            "conversation_name": conversation_name,
            "message": message,
            "answer": timeout_answer,
            "info": timeout_info,
            "plot": None,
            "state": deepcopy(data_source.get("state", STATE)),
            "mode": "ask",
            "actions_taken": [],
            "sources_used": [],
            "source_usage": [],
            "next_recommended_steps": [],
            "needs_human_review": False,
            "human_review_notes": None,
            "web_summary": {},
            "activity_run_id": None,
            "info_panel": timeout_info_panel,
            "mindmap": {},
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
