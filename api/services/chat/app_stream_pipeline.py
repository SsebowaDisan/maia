from __future__ import annotations

from copy import deepcopy
from typing import Any, Generator

from theflow.settings import settings as flowsettings

from maia.base import Document

from ktem.pages.chat.common import STATE

from api.context import ApiContext
from api.schemas import ChatRequest

from .constants import logger
from .conversation_store import persist_conversation
from .fallbacks import fallback_answer_from_exception
from .info_panel_copy import build_info_panel_copy
from .pipeline import create_pipeline
from .verification_contract import VERIFICATION_CONTRACT_VERSION
from .citations import append_required_citation_suffix, normalize_info_evidence_html


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
) -> Generator[dict[str, Any], None, dict[str, Any]]:
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
    if requested_map_type not in {"structure", "evidence", "work_graph", "context_mindmap"}:
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

    info_text = normalize_info_evidence_html(info_text)

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
    info_panel["verification_contract_version"] = VERIFICATION_CONTRACT_VERSION
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
            "attachments": turn_attachments,
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
