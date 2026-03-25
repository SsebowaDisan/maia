from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import json
from typing import Generator

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from api.auth import get_current_user_id
from api.context import get_context
from api.schemas import ChatRequest, ChatResponse
from api.services.observability.citation_trace import begin_trace, end_trace, record_trace_event, summarize_trace
from api.services.chat_service import run_chat_turn, stream_chat_turn

router = APIRouter(prefix="/api/chat", tags=["chat"])
_STREAM_HEARTBEAT_SECONDS = 15.0
logger = logging.getLogger(__name__)


def _to_sse(event: str, payload: dict) -> str:
    data = json.dumps(payload, default=str)
    return f"event: {event}\ndata: {data}\n\n"


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    response: Response,
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    trace = begin_trace(
        kind="chat",
        user_id=user_id,
        question=payload.message,
        conversation_id=payload.conversation_id or "",
    )
    response.headers["X-Maia-Trace-Id"] = trace.trace_id
    try:
        record_trace_event(
            "chat.request_received",
            {
                "agent_mode": payload.agent_mode,
                "conversation_id": payload.conversation_id or "",
                "has_index_selection": bool(payload.index_selection),
                "citation_mode": str(payload.citation or ""),
            },
        )
        result = run_chat_turn(context=context, user_id=user_id, request=payload)
        if isinstance(result, dict):
            info_panel = result.setdefault("info_panel", {})
            if isinstance(info_panel, dict):
                info_panel["trace_id"] = trace.trace_id
                info_panel.setdefault("trace_summary", summarize_trace())
            record_trace_event(
                "chat.response_ready",
                {
                    "conversation_id": str(result.get("conversation_id") or ""),
                    "has_documents": bool(result.get("documents")),
                    "has_blocks": bool(result.get("blocks")),
                    "mode_actually_used": str(result.get("mode_actually_used") or result.get("mode") or ""),
                },
            )
        return result
    except HTTPException as exc:
        record_trace_event(
            "chat.http_error",
            {"status_code": exc.status_code, "detail": str(exc.detail or "")[:500]},
        )
        raise
    except Exception as exc:
        record_trace_event("chat.exception", {"detail": str(exc)[:500]})
        raise
    finally:
        end_trace(trace, level=logging.INFO)


@router.post("/stream")
def chat_stream(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    trace = begin_trace(
        kind="chat_stream",
        user_id=user_id,
        question=payload.message,
        conversation_id=payload.conversation_id or "",
    )

    def event_stream() -> Generator[str, None, None]:
        try:
            record_trace_event(
                "chat_stream.request_received",
                {
                    "agent_mode": payload.agent_mode,
                    "conversation_id": payload.conversation_id or "",
                    "has_index_selection": bool(payload.index_selection),
                    "citation_mode": str(payload.citation or ""),
                },
            )
            iterator = stream_chat_turn(context=context, user_id=user_id, request=payload)
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(next, iterator)
                while True:
                    try:
                        item = pending.result(timeout=_STREAM_HEARTBEAT_SECONDS)
                    except FutureTimeoutError:
                        # Keep the SSE connection active during long orchestration
                        # phases (for example synthesis/polish) so client idle
                        # timeouts do not terminate deep-search runs prematurely.
                        yield _to_sse("ping", {})
                        continue
                    except StopIteration as stop:
                        result = stop.value if isinstance(stop.value, dict) else {}
                        if isinstance(result, dict):
                            info_panel = result.setdefault("info_panel", {})
                            if isinstance(info_panel, dict):
                                info_panel["trace_id"] = trace.trace_id
                                info_panel.setdefault("trace_summary", summarize_trace())
                        record_trace_event(
                            "chat_stream.done",
                            {
                                "conversation_id": str(result.get("conversation_id") or "") if isinstance(result, dict) else "",
                                "has_documents": bool(result.get("documents")) if isinstance(result, dict) else False,
                            },
                        )
                        if isinstance(result, dict):
                            result["trace_id"] = trace.trace_id
                        yield _to_sse("done", result)
                        break

                    event_name = item.get("type", "message") if isinstance(item, dict) else "message"
                    payload_item = item if isinstance(item, dict) else {"value": item}
                    yield _to_sse(event_name, payload_item)
                    pending = executor.submit(next, iterator)
        except HTTPException as exc:
            record_trace_event(
                "chat_stream.http_error",
                {"status_code": exc.status_code, "detail": str(exc.detail or "")[:500]},
            )
            yield _to_sse(
                "error",
                {
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                    "trace_id": trace.trace_id,
                },
            )
        except Exception as exc:
            record_trace_event("chat_stream.exception", {"detail": str(exc)[:500]})
            yield _to_sse(
                "error",
                {
                    "status_code": 500,
                    "detail": str(exc),
                    "trace_id": trace.trace_id,
                },
            )
        finally:
            end_trace(trace, level=logging.INFO)

    response = StreamingResponse(event_stream(), media_type="text/event-stream")
    response.headers["X-Maia-Trace-Id"] = trace.trace_id
    return response
