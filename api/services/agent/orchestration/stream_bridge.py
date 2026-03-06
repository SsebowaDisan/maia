from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.services.agent.execution.interaction_event_contract import normalize_interaction_event
from api.services.agent.live_events import get_live_event_broker
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import ToolExecutionContext, ToolTraceEvent
from api.services.agent.tools.theater_cursor import cursor_payload


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
    def _infer_scene_surface(
        *,
        event_type: str,
        tool_id: str,
        payload: dict[str, Any],
    ) -> str:
        normalized_event = str(event_type or "").strip().lower()
        normalized_tool = str(tool_id or "").strip().lower()

        def _surface_from_url(candidate: Any) -> str:
            url = str(candidate or "").strip().lower()
            if not url:
                return ""
            if "docs.google.com/spreadsheets/" in url:
                return "google_sheets"
            if "docs.google.com/document/" in url:
                return "google_docs"
            if url.startswith("http://") or url.startswith("https://"):
                return "website"
            return ""

        for key in (
            "spreadsheet_url",
            "document_url",
            "source_url",
            "url",
            "target_url",
            "page_url",
            "final_url",
            "link",
        ):
            inferred = _surface_from_url(payload.get(key))
            if inferred:
                return inferred

        if normalized_event.startswith(("browser_", "web_", "brave.", "bing.")):
            return "website"
        if normalized_event.startswith(("email_", "email.", "gmail_", "gmail.")):
            return "email"
        if normalized_event.startswith(("sheet_", "sheets.")) or normalized_event == "drive.go_to_sheet":
            return "google_sheets"
        if normalized_event.startswith(("document_", "pdf_")):
            return "document"
        if normalized_event.startswith(("doc_", "docs.")) or normalized_event == "drive.go_to_doc":
            return "google_docs"
        if normalized_event.startswith("drive."):
            if normalized_tool.startswith("workspace.sheets."):
                return "google_sheets"
            if normalized_tool.startswith("workspace.docs."):
                return "google_docs"
            return "document"

        if normalized_tool.startswith(("workspace.docs.", "docs.create")):
            return "google_docs"
        if normalized_tool.startswith("documents.highlight."):
            return "document"
        if normalized_tool.startswith("workspace.sheets."):
            return "google_sheets"
        if normalized_tool.startswith(("browser.", "marketing.web_research", "web.extract.", "web.dataset.")):
            return "website"
        if normalized_tool.startswith(("gmail.", "email.")):
            return "email"

        return "system"

    @staticmethod
    def _trace_payload(trace: ToolTraceEvent | Any) -> dict[str, Any] | None:
        if isinstance(trace, ToolTraceEvent):
            return trace.to_dict()
        if hasattr(trace, "to_dict"):
            raw = trace.to_dict()
            return raw if isinstance(raw, dict) else None
        return dict(trace) if isinstance(trace, dict) else None

    @staticmethod
    def _read_index_value(payload: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            raw = payload.get(key)
            if raw is None:
                continue
            try:
                parsed = int(raw)
            except Exception:
                continue
            if parsed > 0:
                return parsed
        return None

    @staticmethod
    def _enrich_interaction_payload(
        *,
        event_type: str,
        tool_id: str,
        step_index: int,
        detail: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_event = str(event_type or "").strip().lower()
        normalized_surface = str(payload.get("scene_surface") or "").strip().lower()
        interactive_surface = normalized_surface in {
            "website",
            "document",
            "google_docs",
            "google_sheets",
            "email",
        }
        interactive_event = normalized_event.startswith(
            (
                "browser_",
                "web_",
                "pdf_",
                "doc_",
                "docs.",
                "sheet_",
                "sheets.",
                "drive.",
            )
        )
        if not interactive_surface and not interactive_event:
            return payload

        has_cursor = payload.get("cursor_x") is not None and payload.get("cursor_y") is not None
        primary_index = LiveRunStream._read_index_value(
            payload,
            "primary_index",
            "variant_index",
            "page_index",
            "scan_pass",
            "step",
        )
        secondary_index = LiveRunStream._read_index_value(
            payload,
            "secondary_index",
            "result_rank",
            "page_total",
            "scan_pass",
        )
        primary = primary_index or max(1, int(step_index) + 1)
        secondary = secondary_index or 1
        if not has_cursor:
            payload.update(
                cursor_payload(
                    lane=f"{tool_id}:{normalized_event or 'interaction'}",
                    primary_index=primary,
                    secondary_index=secondary,
                )
            )

        if normalized_event == "browser_scroll":
            if not str(payload.get("scroll_direction") or "").strip():
                payload["scroll_direction"] = "up" if "up" in detail.lower() else "down"
            if payload.get("scroll_percent") is None:
                payload["scroll_percent"] = round(min(96.0, max(4.0, float(primary * 12))), 2)

        return payload

    def stream_traces(
        self,
        *,
        step: PlannedStep,
        step_index: int,
        traces: list[ToolTraceEvent] | list[Any],
        activity_event_factory: Callable[..., AgentActivityEvent],
    ) -> Generator[dict[str, Any], None, None]:
        for trace in list(traces or []):
            payload_raw = self._trace_payload(trace)
            if not isinstance(payload_raw, dict):
                continue
            raw_event_type = str(payload_raw.get("event_type") or "tool_progress").strip()
            raw_data = payload_raw.get("data")
            raw_data_dict = dict(raw_data) if isinstance(raw_data, dict) else {}
            default_surface = self._infer_scene_surface(
                event_type=raw_event_type,
                tool_id=step.tool_id,
                payload=raw_data_dict,
            )
            payload = normalize_interaction_event(
                payload_raw,
                default_scene_surface=default_surface,
            )
            trace_event_type = str(payload.get("event_type") or "tool_progress").strip()
            trace_title = str(payload.get("title") or step.title).strip() or step.title
            trace_detail = str(payload.get("detail") or "").strip()
            trace_data = payload.get("data")
            trace_data_dict = dict(trace_data) if isinstance(trace_data, dict) else {}
            if not str(trace_data_dict.get("scene_surface") or "").strip():
                trace_data_dict["scene_surface"] = self._infer_scene_surface(
                    event_type=trace_event_type,
                    tool_id=step.tool_id,
                    payload=trace_data_dict,
                )
            trace_data_dict = self._enrich_interaction_payload(
                event_type=trace_event_type,
                tool_id=step.tool_id,
                step_index=step_index,
                detail=trace_detail,
                payload=trace_data_dict,
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
