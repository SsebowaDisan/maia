from __future__ import annotations

import json
from typing import Generator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.auth import get_current_user_id
from api.context import get_context
from api.schemas import ChatRequest, ChatResponse
from api.services.chat_service import run_chat_turn, stream_chat_turn

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _to_sse(event: str, payload: dict) -> str:
    data = json.dumps(payload, default=str)
    return f"event: {event}\ndata: {data}\n\n"


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    return run_chat_turn(context=context, user_id=user_id, request=payload)


@router.post("/stream")
def chat_stream(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()

    def event_stream() -> Generator[str, None, None]:
        try:
            iterator = stream_chat_turn(context=context, user_id=user_id, request=payload)
            while True:
                item = next(iterator)
                event_name = item.get("type", "message")
                yield _to_sse(event_name, item)
        except StopIteration as stop:
            result = stop.value
            yield _to_sse("done", result)
        except HTTPException as exc:
            yield _to_sse(
                "error",
                {
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                },
            )
        except Exception as exc:
            yield _to_sse(
                "error",
                {
                    "status_code": 500,
                    "detail": str(exc),
                },
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")

