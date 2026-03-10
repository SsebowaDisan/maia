from __future__ import annotations

from queue import Empty

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.auth import get_current_user_id
from api.services.agent.live_events import LiveEventSubscription, get_live_event_broker

from .common import to_sse

router = APIRouter(tags=["agent"])


@router.get("/events")
def stream_agent_events(
    run_id: str | None = None,
    replay: int = Query(default=0, ge=0, le=200000),
    user_id: str = Depends(get_current_user_id),
):
    broker = get_live_event_broker()
    subscription = broker.subscribe(user_id=user_id, run_id=run_id, replay_limit=replay)

    def event_stream(active_subscription: LiveEventSubscription):
        try:
            yield to_sse("ready", {"status": "subscribed", "run_id": run_id})
            while True:
                event = broker.receive(active_subscription, timeout_seconds=15)
                if event is None:
                    yield ": keep-alive\n\n"
                    continue
                yield to_sse("event", event)
        except Empty:
            yield ": keep-alive\n\n"
        finally:
            broker.unsubscribe(active_subscription)

    return StreamingResponse(event_stream(subscription), media_type="text/event-stream")
