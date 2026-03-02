from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.services.agent.live_events import get_live_event_broker
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import ToolExecutionContext, ToolTraceEvent


class LiveRunStream:
    def __init__(
        self,
        *,
        activity_store: Any,
        user_id: str,
        run_id: str,
        observed_event_types: list[str],
    ) -> None:
        self.activity_store = activity_store
        self.user_id = user_id
        self.run_id = run_id
        self.observed_event_types = observed_event_types

    def emit(self, event: AgentActivityEvent) -> dict[str, Any]:
        self.observed_event_types.append(event.event_type)
        self.activity_store.append(event)
        get_live_event_broker().publish(
            user_id=self.user_id,
            run_id=self.run_id,
            event={
                "type": event.event_type,
                "message": event.title,
                "data": event.data,
                "run_id": self.run_id,
                "event_id": event.event_id,
                "seq": event.seq,
            },
        )
        return {"type": "activity", "event": event.to_dict()}

    @staticmethod
    def _trace_payload(trace: ToolTraceEvent | Any) -> dict[str, Any] | None:
        if isinstance(trace, ToolTraceEvent):
            return trace.to_dict()
        if hasattr(trace, "to_dict"):
            raw = trace.to_dict()
            return raw if isinstance(raw, dict) else None
        return dict(trace) if isinstance(trace, dict) else None

    def stream_traces(
        self,
        *,
        step: PlannedStep,
        step_index: int,
        traces: list[ToolTraceEvent] | list[Any],
        activity_event_factory: Callable[..., AgentActivityEvent],
    ) -> Generator[dict[str, Any], None, None]:
        for trace in list(traces or []):
            payload = self._trace_payload(trace)
            if not isinstance(payload, dict):
                continue
            trace_event_type = str(payload.get("event_type") or "tool_progress").strip()
            trace_title = str(payload.get("title") or step.title).strip() or step.title
            trace_detail = str(payload.get("detail") or "").strip()
            trace_data = payload.get("data")
            trace_data_dict = dict(trace_data) if isinstance(trace_data, dict) else {}
            if "scene_surface" not in trace_data_dict:
                trace_data_dict["scene_surface"] = (
                    "preview"
                    if trace_event_type.startswith(("browser_", "web_"))
                    else "system"
                )
            trace_snapshot = payload.get("snapshot_ref")
            trace_event = activity_event_factory(
                event_type=trace_event_type,
                title=trace_title,
                detail=trace_detail,
                metadata={
                    **trace_data_dict,
                    "tool_id": step.tool_id,
                    "step": step_index,
                },
                snapshot_ref=str(trace_snapshot) if trace_snapshot else None,
            )
            yield self.emit(trace_event)

    def run_tool_live(
        self,
        *,
        registry: Any,
        step: PlannedStep,
        step_index: int,
        execution_context: ToolExecutionContext,
        access_context: Any,
        prompt: str,
        params: dict[str, Any],
        activity_event_factory: Callable[..., AgentActivityEvent],
    ) -> Generator[dict[str, Any], None, Any]:
        execution_stream = registry.execute_with_trace(
            tool_id=step.tool_id,
            context=execution_context,
            access=access_context,
            prompt=prompt,
            params=params,
        )
        while True:
            try:
                trace = next(execution_stream)
            except StopIteration as stop:
                return stop.value
            for trace_event in self.stream_traces(
                step=step,
                step_index=step_index,
                traces=[trace],
                activity_event_factory=activity_event_factory,
            ):
                yield trace_event
