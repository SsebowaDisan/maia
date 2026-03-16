from __future__ import annotations

import time
from copy import deepcopy
from datetime import datetime
import re as _re
from typing import Any, Callable, Generator

from tzlocal import get_localzone

from maia.mindmap.indexer import build_knowledge_map as _build_knowledge_map

from api.services.chat.block_builder import build_turn_blocks
from api.schemas import ChatRequest, HaltReason
from api.services import mindmap_service
from api.services.agent.orchestrator import get_orchestrator

from api.services.agent.session_pool import SessionPool

from .constants import logger
from .fallbacks import fallback_answer_from_exception

# Human-readable messages keyed by HaltReason for the halt SSE event.
_HALT_MESSAGES: dict[str, str] = {
    "llm_quota_exceeded": "The agent hit a usage limit — showing best available answer.",
    "tool_failure": "A tool failed during research — answer may be incomplete.",
    "llm_timeout": "Response took too long — showing best available answer.",
    "context_too_large": "Context exceeded the model limit — showing best available answer.",
    "no_snippets": "No relevant sources found for this question.",
    "no_relevant_snippets": "No sufficiently relevant sources found for this question.",
    "mode_downgraded": "Switched to quick answer mode — the requested mode could not complete.",
}


def _classify_orchestrator_exception(exc: Exception) -> HaltReason:
    """Map an orchestrator exception to the most specific HaltReason."""
    msg = str(exc).lower()
    if any(t in msg for t in ("quota", "429", "rate limit", "rate_limit", "too many requests")):
        return HaltReason.llm_quota_exceeded
    if any(t in msg for t in ("content policy", "content_filter", "moderation", "content filtered")):
        return HaltReason.tool_failure
    if any(t in msg for t in ("timeout", "timed out", "deadline")):
        return HaltReason.llm_timeout
    if any(t in msg for t in ("context length", "context_length", "max_tokens", "token limit")):
        return HaltReason.context_too_large
    return HaltReason.tool_failure
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
    _turn_start_ms = int(time.monotonic() * 1000)
    # Acquire a warm session from the pool.  The session caches resolved LLM
    # config so repeated turns skip cold-construction overhead.  acquire() never
    # raises — a fresh blank session is returned on first use or pool miss.
    _session = SessionPool.acquire(user_id=user_id, conversation_id=conversation_id)
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
    if requested_mode == "company_agent" and context_summary and not existing_goal:
        # Strip emails and URLs from injected context so they cannot bleed into
        # task_understanding.py's _extract_first_email / _extract_first_url scans.
        # The full context is still available to the agent via agent_settings below.
        safe_context = _re.sub(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[email]", context_summary
        )
        safe_context = _re.sub(r"https?://[^\s\])>\"',]+", "[url]", safe_context)
        agent_goal_parts.append(f"Conversation context: {safe_context}")
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

    # B-03: Resolve marketplace/installed agent from @mention or LLM intent.
    # When an agent is resolved, its tool allowlist and system prompt are injected
    # so that the step planner respects the agent's declared capability scope.
    try:
        from api.services.agents.resolver import resolve_agent
        from api.services.agents.definition_store import get_agent, load_schema as _load_schema

        _resolution = resolve_agent(user_id, message, user_id=user_id)
        if _resolution:
            _agent_record = get_agent(user_id, _resolution.agent_id)
            if _agent_record:
                _agent_schema = _load_schema(_agent_record)
                if getattr(_agent_schema, "tools", None):
                    agent_settings["__allowed_tool_ids"] = list(_agent_schema.tools)
                # Prepend agent system_prompt to agent_goal so task_preparation
                # picks it up as execution context (same approach as runner.py).
                _sys_prompt = getattr(_agent_schema, "system_prompt", None) or ""
                if _sys_prompt:
                    _cur_goal = str(getattr(agent_request, "agent_goal", "") or "")
                    _new_goal = f"{_sys_prompt}\n\n{_cur_goal}".strip()[:1200] if _cur_goal else _sys_prompt[:1200]
                    try:
                        agent_request = agent_request.model_copy(update={"agent_goal": _new_goal})
                    except Exception:
                        pass
                logger.debug(
                    "Resolved agent %s (by=%s) for user=%s",
                    _resolution.agent_id,
                    _resolution.matched_by,
                    user_id,
                )
    except Exception:
        logger.debug("Agent resolution failed — proceeding with default mode", exc_info=True)

    if requested_mode == _DEEP_SEARCH_MODE:
        agent_settings["__deep_search_enabled"] = True
    if context_snippets:
        agent_settings["__conversation_snippets"] = context_snippets
    if context_summary:
        # Sanitize emails and URLs from conversation summary before it reaches
        # task_preparation → llm_contracts → next_steps generation, preventing
        # prior-turn email addresses from appearing in recommended next steps.
        _safe_summary = _re.sub(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[email]", context_summary
        )
        _safe_summary = _re.sub(r"https?://[^\s\])>\"',]+", "[url]", _safe_summary)
        agent_settings["__conversation_summary"] = _safe_summary
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
        _halt = _classify_orchestrator_exception(exc)
        logger.warning(
            "orchestrator_stop condition=%s error=%s", _halt, str(exc)[:200]
        )
        logger.exception("Orchestrator execution failed: %s", exc)
        yield {
            "type": "halt",
            "reason": _halt,
            "message": _HALT_MESSAGES.get(_halt, "An error occurred — showing best available answer."),
        }
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
                "__halt_reason": _halt,
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
    try:
        plot_data = extract_plot_from_actions_fn(agent_result.actions_taken)
    except Exception:
        logger.exception("Plot extraction failed; continuing without plot event")
        plot_data = None
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
                    answer_text=answer_text,
                    map_type="work_graph",
                    max_depth=max(2, min(8, requested_mindmap_depth)),
                    include_reasoning_map=bool(agent_mindmap_settings.get("include_reasoning_map", True)),
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
                        answer_text=answer_text,
                        map_type="work_graph",
                        max_depth=max(2, min(8, requested_mindmap_depth)),
                        include_reasoning_map=bool(agent_mindmap_settings.get("include_reasoning_map", True)),
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
                        answer_text=answer_text,
                        map_type=requested_map_type,
                        max_depth=max(2, min(8, requested_mindmap_depth)),
                        include_reasoning_map=bool(agent_mindmap_settings.get("include_reasoning_map", True)),
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

    blocks, documents = build_turn_blocks(
        answer_text=answer_text,
        question=message,
        workspace_ids=captured_workspace_ids,
    )

    messages = chat_history + [[message, answer_text]]
    retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
    retrieval_history.append(normalized_agent_info_html)
    plot_history = deepcopy(data_source.get("plot_history", []))
    plot_history.append(plot_data)
    _agent_halt_reason = getattr(agent_result, "__halt_reason", None)
    _orch_perf: dict[str, Any] = {
        "snippets_retrieved": None,
        "snippets_after_focus": None,
        "snippets_sent_to_llm": None,
        "snippets_cited": None,
        "retrieval_score_avg": None,
        "retrieval_score_p50": None,
        "context_tokens_used": None,
        "context_tokens_budget": None,
        "mode_requested": requested_mode,
        "mode_actually_used": requested_mode,
        "halt_reason": _agent_halt_reason,
        "mindmap_generated": bool(mindmap_payload),
        "focus_applied": False,
        "focus_filter_count_before": None,
        "focus_filter_count_after": None,
        "retrieval_ms": None,
        "llm_ms": None,
        "total_turn_ms": int(time.monotonic() * 1000) - _turn_start_ms,
    }
    info_panel["perf"] = _orch_perf
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
            "blocks": blocks,
            "documents": documents,
            "halt_reason": _agent_halt_reason,
            "mode_actually_used": requested_mode,
            "perf": _orch_perf,
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
    SessionPool.release(user_id=user_id, conversation_id=conversation_id)

    return {
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "message": message,
        "answer": answer_text,
        "blocks": blocks,
        "documents": documents,
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
        "mode_actually_used": requested_mode,
        "halt_reason": _agent_halt_reason,
    }
