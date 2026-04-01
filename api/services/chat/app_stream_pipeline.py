from __future__ import annotations

import time
from copy import deepcopy
from typing import Any, Generator

from theflow.settings import settings as flowsettings

from maia.base import Document

from ktem.pages.chat.common import STATE

from api.context import ApiContext
from api.services.chat.block_builder import build_turn_blocks
from api.schemas import ChatRequest

from maia.mindmap.indexer import build_reasoning_map as _build_reasoning_map_from_indexer

from api.schemas import HaltReason

from .constants import logger
from .conversation_store import persist_conversation
from .canvas_turn import attach_canvas_document
from .fallbacks import fallback_answer_from_exception
from .info_panel_copy import build_info_panel_copy
from .pipeline import create_pipeline
from .verification_contract import VERIFICATION_CONTRACT_VERSION
from .citations import append_required_citation_suffix, normalize_info_evidence_html


def _enrich_pipeline_mindmap_reasoning(
    mindmap_payload: dict,
    *,
    question: str,
    answer_text: str,
    mindmap_settings: dict,
) -> None:
    """Post-stream: rebuild reasoning_map with the final answer text using LLM steps.

    The pipeline builds its mindmap mid-stream before the full answer is available.
    This function replaces the reasoning_map once the answer is complete, giving the
    LLM step generator the full answer context.  Mutates mindmap_payload in-place.
    """
    if not bool(mindmap_settings.get("include_reasoning_map", True)):
        return
    if not answer_text.strip():
        return
    try:
        from api.services.mindmap_service import _generate_reasoning_steps_llm

        reasoning_steps = _generate_reasoning_steps_llm(answer_text, question) or None
        if not reasoning_steps:
            return

        nodes = mindmap_payload.get("nodes", [])
        # Re-select context nodes by Jaccard similarity (same logic as indexer)
        from maia.mindmap.indexer import _build_reasoning_context_nodes
        context_nodes = _build_reasoning_context_nodes(
            list(nodes) if isinstance(nodes, list) else [],
            question=question,
            answer_text=answer_text,
        )
        mindmap_payload["reasoning_map"] = _build_reasoning_map_from_indexer(
            question=question,
            answer_text=answer_text,
            context_nodes=context_nodes,
            reasoning_steps=reasoning_steps,
        )
    except Exception as exc:
        logger.warning("pipeline_mindmap_reasoning_enrich_failed error=%s", exc)


def run_pipeline_stream_turn(
    *,
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
    settings: dict[str, Any],
    chat_state: dict[str, Any],
    selected_payload: dict[str, Any],
    message: str,
    conversation_id: str,
    conversation_name: str,
    chat_history: list[list[str]],
    data_source: dict[str, Any],
    turn_attachments: list[dict[str, str]],
    requested_mode: str,
    mode_variant: str,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    pipeline, reasoning_state, reasoning_id = create_pipeline(
        context=context,
        settings=settings,
        request=request,
        user_id=user_id,
        state=chat_state,
        selected_by_index=selected_payload,
    )

    _turn_start_ms = int(time.monotonic() * 1000)
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
    if requested_map_type not in {"structure", "evidence", "work_graph", "context_mindmap"}:
        requested_map_type = "structure"
    try:
        for response in pipeline.stream(
            message,
            conversation_id,
            chat_history,
            mindmap_focus=request.mindmap_focus.model_dump() if hasattr(request.mindmap_focus, "model_dump") else dict(request.mindmap_focus or {}),
            mindmap_max_depth=max(2, min(8, requested_mindmap_depth)),
            include_reasoning_map=bool(mindmap_settings.get("include_reasoning_map", True)),
            mindmap_map_type=requested_map_type,
        ):
            if not isinstance(response, Document) or response.channel is None:
                continue

            if response.channel == "chat":
                if response.content is None:
                    # Some reasoning pipelines emit a reset signal before sending
                    # a canonical final answer (for example replacing streamed raw text
                    # with citation-linked text). Keep only the canonical answer.
                    answer_text = ""
                    continue
                delta = str(response.content or "")
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

    pipeline_halt_reason: HaltReason | None = None
    if pipeline_error is not None and not answer_text:
        pipeline_halt_reason = HaltReason.tool_failure
        yield {
            "type": "halt",
            "reason": pipeline_halt_reason,
            "message": "A pipeline error occurred — showing best available answer.",
        }
        answer_text = fallback_answer_from_exception(pipeline_error)
        yield {"type": "chat_delta", "delta": answer_text, "text": answer_text}

    if not answer_text:
        answer_text = getattr(
            flowsettings,
            "KH_CHAT_EMPTY_MSG_PLACEHOLDER",
            "(Sorry, I don't know)",
        )
        yield {"type": "chat_delta", "delta": answer_text, "text": answer_text}

    info_text = normalize_info_evidence_html(info_text)

    # Enrich the pipeline mindmap's reasoning_map with the complete answer text.
    # The pipeline emits its mindmap mid-stream before the answer is finished, so
    # the reasoning steps were generated from a partial answer.  Replace them now.
    if mindmap_payload and bool(request.use_mindmap):
        _enrich_pipeline_mindmap_reasoning(
            mindmap_payload,
            question=message,
            answer_text=answer_text,
            mindmap_settings=mindmap_settings,
        )

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
    display_mode = mode_variant or requested_mode or "ask"
    info_panel = build_info_panel_copy(
        request_message=message,
        answer_text=answer_text,
        info_html=info_text,
        mode="ask",
        next_steps=[],
        web_summary={},
    )
    info_panel["verification_contract_version"] = VERIFICATION_CONTRACT_VERSION
    if mode_variant:
        info_panel["mode_variant"] = mode_variant
    if mindmap_payload:
        info_panel["mindmap"] = mindmap_payload
    _pipeline_perf: dict[str, Any] = {
        "snippets_retrieved": None,
        "snippets_after_focus": None,
        "snippets_sent_to_llm": None,
        "snippets_cited": None,
        "retrieval_score_avg": None,
        "retrieval_score_p50": None,
        "context_tokens_used": None,
        "context_tokens_budget": None,
        "mode_requested": display_mode,
        "mode_actually_used": display_mode,
        "halt_reason": pipeline_halt_reason,
        "mindmap_generated": bool(mindmap_payload),
        "focus_applied": False,
        "focus_filter_count_before": None,
        "focus_filter_count_after": None,
        "retrieval_ms": None,
        "llm_ms": None,
        "total_turn_ms": int(time.monotonic() * 1000) - _turn_start_ms,
    }
    info_panel["perf"] = _pipeline_perf
    blocks, documents = build_turn_blocks(answer_text=answer_text, question=message)
    blocks, documents, canvas_payload = attach_canvas_document(
        user_id=user_id,
        question=message,
        answer_text=answer_text,
        info_html=info_text,
        info_panel=info_panel,
        mode_variant=display_mode,
        blocks=blocks,
        documents=documents,
    )
    if canvas_payload:
        info_panel["canvas_document_id"] = str(canvas_payload.get("id") or "")
        info_panel["canvas_title"] = str(canvas_payload.get("title") or "")

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
            "attachments": turn_attachments,
            "next_recommended_steps": [],
            "needs_human_review": False,
            "human_review_notes": None,
            "web_summary": {},
            "info_panel": info_panel,
            "mindmap": mindmap_payload,
            "blocks": blocks,
            "documents": documents,
            "halt_reason": pipeline_halt_reason,
            "mode_requested": display_mode,
            "mode_actually_used": display_mode,
            "perf": _pipeline_perf,
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
        "blocks": blocks,
        "documents": documents,
        "info": info_text,
        "plot": plot_data,
        "state": chat_state,
        "mode": "ask",
        "halt_reason": pipeline_halt_reason,
        "mode_requested": display_mode,
        "mode_actually_used": display_mode,
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
