from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import json
from typing import Generator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.auth import get_current_user_id
from api.context import get_context
from api.schemas import ChatRequest, ChatResponse
from api.services.chat_service import run_chat_turn, stream_chat_turn

router = APIRouter(prefix="/api/chat", tags=["chat"])
_STREAM_HEARTBEAT_SECONDS = 15.0


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
                        yield _to_sse("done", result)
                        break

                    event_name = item.get("type", "message") if isinstance(item, dict) else "message"
                    payload_item = item if isinstance(item, dict) else {"value": item}
                    yield _to_sse(event_name, payload_item)
                    pending = executor.submit(next, iterator)
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
