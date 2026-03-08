from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Generator

from tzlocal import get_localzone

from maia.mindmap.indexer import build_knowledge_map as _build_knowledge_map

from api.schemas import ChatRequest
from api.services import mindmap_service
from api.services.agent.orchestrator import get_orchestrator

from .constants import logger
from .fallbacks import fallback_answer_from_exception
from .info_panel_copy import build_info_panel_copy
from .streaming import chunk_text_for_stream, make_activity_stream_event, build_agent_context_window
from .verification_contract import (
    VERIFICATION_CONTRACT_VERSION,
    build_web_review_content,
    normalize_verification_evidence_items,
)
from .citations import enforce_required_citations, normalize_info_evidence_html
from .conversation_store import persist_conversation
from .app_prompt_helpers import _DEEP_SEARCH_MODE


def run_orchestrator_stream_turn(
    *,
    request: ChatRequest,
    user_id: str,
    message: str,
    settings: dict[str, Any],
    conversation_id: str,
    conversation_name: str,
    data_source: dict[str, Any],
    chat_history: list[list[str]],
    chat_state: dict[str, Any],
    persisted_workspace_ids: dict[str, str],
    selected_payload: dict[str, Any],
    turn_attachments: list[dict[str, str]],
    requested_mode: str,
    mode_variant: str,
    capture_workspace_ids_from_actions_fn: Callable[[list[Any]], dict[str, str]],
    extract_plot_from_actions_fn: Callable[[list[Any]], dict[str, Any] | None],
) -> Generator[dict[str, Any], None, dict[str, Any]]:
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
    if requested_mode == "company_agent" and context_summary:
        agent_goal_parts.append(f"Conversation context: {context_summary}")
    contextual_goal = " ".join(agent_goal_parts).strip()[:900]
    agent_request = request
    if contextual_goal and contextual_goal != existing_goal:
        try:
            agent_request = agent_request.model_copy(update={"agent_goal": contextual_goal})
        except Exception:
            request_payload = agent_request.model_dump()
            request_payload["agent_goal"] = contextual_goal
            agent_request = ChatRequest(**request_payload)
    agent_settings = dict(settings)
    if isinstance(request.setting_overrides, dict):
        agent_settings.update(request.setting_overrides)
    if requested_mode == _DEEP_SEARCH_MODE:
        agent_settings["__deep_search_enabled"] = True
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
        logger.exception("Orchestrator execution failed: %s", exc)
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
                "evidence_items": [],
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
    normalized_agent_info_html = normalize_info_evidence_html(
        str(getattr(agent_result, "info_html", "") or "")
    )
    if normalized_agent_info_html:
        yield {"type": "info_delta", "delta": normalized_agent_info_html}
    pre_citation_answer_text = answer_text
    answer_text = enforce_required_citations(
        answer=answer_text,
        info_html=normalized_agent_info_html,
        citation_mode=request.citation,
    )
    if answer_text != pre_citation_answer_text:
        if answer_text.startswith(pre_citation_answer_text):
            delta = answer_text[len(pre_citation_answer_text) :]
            if delta:
                yield {
                    "type": "chat_delta",
                    "delta": delta,
                    "text": answer_text,
                }
        else:
            # Citation normalization may rewrite body text, so stream a canonical replacement.
            yield {
                "type": "chat_delta",
                "delta": answer_text,
                "text": answer_text,
            }
    plot_data = extract_plot_from_actions_fn(agent_result.actions_taken)
    if plot_data:
        yield {"type": "plot", "plot": plot_data}
    agent_web_summary = (
        dict(getattr(agent_result, "web_summary", {}))
        if isinstance(getattr(agent_result, "web_summary", {}), dict)
        else {}
    )
    mindmap_payload: dict[str, Any] = {}
    if bool(request.use_mindmap):
        agent_mindmap_settings = dict(request.mindmap_settings or {})
        try:
            requested_mindmap_depth = int(agent_mindmap_settings.get("max_depth", 4))
        except Exception:
            requested_mindmap_depth = 4
        requested_map_type = str(
            agent_mindmap_settings.get("map_type", "context_mindmap") or "context_mindmap"
        ).strip().lower()
        if requested_map_type not in {"structure", "evidence", "work_graph", "context_mindmap"}:
            requested_map_type = "context_mindmap"
        action_rows = [
            item.to_dict() if hasattr(item, "to_dict") else dict(item)
            for item in list(getattr(agent_result, "actions_taken", []) or [])
            if isinstance(item, dict) or hasattr(item, "to_dict")
        ]
        source_rows = [
            item.to_dict() if hasattr(item, "to_dict") else dict(item)
            for item in list(getattr(agent_result, "sources_used", []) or [])
            if isinstance(item, dict) or hasattr(item, "to_dict")
        ]
        if action_rows or source_rows:
            if requested_map_type == "work_graph":
                # Work graph: execution-based branched tree (Planning / Research / Evidence)
                mindmap_payload = mindmap_service.build_agent_work_graph(
                    request_message=message,
                    actions_taken=action_rows,
                    sources_used=source_rows,
                    map_type="work_graph",
                    max_depth=max(2, min(8, requested_mindmap_depth)),
                    run_id=str(getattr(agent_result, "run_id", "") or ""),
                )
            else:
                # NotebookLM approach: LLM-generated conceptual tree from answer content.
                # Root = question topic; branches = major themes in the answer;
                # leaves = supporting details. Same method as fast_qa and NotebookLM.
                source_docs = []
                for _si, _row in enumerate(source_rows[:20]):
                    if not isinstance(_row, dict):
                        continue
                    _text = str(
                        _row.get("text") or _row.get("snippet") or
                        _row.get("summary") or _row.get("label") or ""
                    )
                    source_docs.append({
                        "doc_id": str(_row.get("file_id") or _row.get("url") or f"src_{_si + 1}"),
                        "text": _text,
                        "metadata": {
                            "source_name": str(_row.get("label") or _row.get("url") or ""),
                            "source_id": str(_row.get("file_id") or ""),
                        },
                    })
                _context_text = answer_text or "\n\n".join(
                    d["text"] for d in source_docs[:8] if d.get("text")
                )
                try:
                    cm_payload = _build_knowledge_map(
                        question=message,
                        context=_context_text,
                        documents=source_docs,
                        answer_text=answer_text,
                        max_depth=max(2, min(8, requested_mindmap_depth)),
                        include_reasoning_map=bool(
                            agent_mindmap_settings.get("include_reasoning_map", True)
                        ),
                        source_type_hint="",
                        focus={},
                        map_type="structure",
                    )
                    # Apply the requested map_type label
                    cm_payload["map_type"] = requested_map_type
                    cm_payload["kind"] = requested_map_type
                    if isinstance(cm_payload.get("settings"), dict):
                        cm_payload["settings"]["map_type"] = requested_map_type
                    # Always include the work graph as a switchable variant
                    _wg = mindmap_service.build_agent_work_graph(
                        request_message=message,
                        actions_taken=action_rows,
                        sources_used=source_rows,
                        map_type="work_graph",
                        max_depth=max(2, min(8, requested_mindmap_depth)),
                        run_id=str(getattr(agent_result, "run_id", "") or ""),
                    )
                    _variants = dict(cm_payload.get("variants") or {})
                    _variants["work_graph"] = _wg
                    cm_payload["variants"] = _variants
                    mindmap_payload = cm_payload
                except Exception:
                    # Fallback: use the execution graph if LLM concept extraction fails
                    mindmap_payload = mindmap_service.build_agent_work_graph(
                        request_message=message,
                        actions_taken=action_rows,
                        sources_used=source_rows,
                        map_type=requested_map_type,
                        max_depth=max(2, min(8, requested_mindmap_depth)),
                        run_id=str(getattr(agent_result, "run_id", "") or ""),
                    )
    info_panel = build_info_panel_copy(
        request_message=message,
        answer_text=answer_text,
        info_html=normalized_agent_info_html,
        mode=requested_mode,
        next_steps=list(getattr(agent_result, "next_recommended_steps", []) or []),
        web_summary=agent_web_summary,
    )
    info_panel["verification_contract_version"] = VERIFICATION_CONTRACT_VERSION
    raw_agent_evidence_items = getattr(agent_result, "evidence_items", [])
    if isinstance(raw_agent_evidence_items, list):
        normalized_evidence_items = normalize_verification_evidence_items(raw_agent_evidence_items)
        if normalized_evidence_items:
            info_panel["evidence_items"] = normalized_evidence_items
            web_review_content = build_web_review_content(normalized_evidence_items)
            if web_review_content:
                info_panel["web_review_content"] = web_review_content
    if mode_variant:
        info_panel["mode_variant"] = mode_variant
    if mindmap_payload:
        info_panel["mindmap"] = mindmap_payload

    chat_state.setdefault("app", {})
    chat_state["app"]["last_agent_run_id"] = agent_result.run_id
    captured_workspace_ids = capture_workspace_ids_from_actions_fn(agent_result.actions_taken)
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
    retrieval_history.append(normalized_agent_info_html)
    plot_history = deepcopy(data_source.get("plot_history", []))
    plot_history.append(plot_data)
    message_meta = deepcopy(data_source.get("message_meta", []))
    message_meta.append(
        {
            "mode": requested_mode,
            "activity_run_id": agent_result.run_id or None,
            "actions_taken": [item.to_dict() for item in agent_result.actions_taken],
            "sources_used": [item.to_dict() for item in agent_result.sources_used],
            "source_usage": [],
            "attachments": turn_attachments,
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
        "info": normalized_agent_info_html,
        "plot": plot_data,
        "state": chat_state,
        "mode": requested_mode,
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
