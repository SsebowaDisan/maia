from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.services.agent.execution.interaction_event_contract import normalize_interaction_event
from api.services.agent.live_events import get_live_event_broker
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import ToolExecutionContext, ToolTraceEvent
from api.services.agent.tools.theater_cursor import cursor_payload
from api.services.agent.zoom_history import enrich_event_data_with_zoom
from .role_contracts import resolve_owner_role_for_tool


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
        self._latest_copy_by_surface: dict[str, dict[str, Any]] = {}
        self._latest_copy_any: dict[str, Any] | None = None

    def emit(self, event: AgentActivityEvent) -> dict[str, Any]:
        event_data = dict(event.data or {})
        event_index = (
            int(event.seq)
            if isinstance(event.seq, int) and event.seq > 0
            else len(self.observed_event_types) + 1
        )
        graph_node_id = str(event_data.get("graph_node_id") or "").strip()
        scene_ref = str(event_data.get("scene_ref") or "").strip()
        replay_importance = str(event_data.get("event_replay_importance") or "").strip()
        event_data = enrich_event_data_with_zoom(
            data=event_data,
            event_type=event.event_type,
            event_id=event.event_id,
            event_index=event_index,
            timestamp=event.timestamp,
            graph_node_id=graph_node_id,
            scene_ref=scene_ref,
        )
        event_data = self._enrich_copy_provenance(
            event=event,
            payload=event_data,
            event_index=event_index,
            graph_node_id=graph_node_id,
            scene_ref=scene_ref,
        )
        graph_node_id = str(event_data.get("graph_node_id") or graph_node_id).strip()
        scene_ref = str(event_data.get("scene_ref") or scene_ref).strip()
        event_data.setdefault("event_index", event_index)
        if graph_node_id:
            event_data.setdefault("graph_node_id", graph_node_id)
        if scene_ref:
            event_data.setdefault("scene_ref", scene_ref)
        if replay_importance:
            event_data.setdefault("replay_importance", replay_importance)
        event_data.setdefault(
            "timeline",
            {
                "event_index": event_index,
                "replay_importance": replay_importance or "normal",
                "graph_node_id": graph_node_id or None,
                "scene_ref": scene_ref or None,
            },
        )
        event.data = dict(event_data)
        event.metadata = dict(event_data)
        self.observed_event_types.append(event.event_type)
        self.activity_store.append(event)
        event_family = str(event_data.get("event_family") or "").strip()
        event_priority = str(event_data.get("event_priority") or "").strip()
        event_render_mode = str(event_data.get("event_render_mode") or "").strip()
        get_live_event_broker().publish(
            user_id=self.user_id,
            run_id=self.run_id,
            event={
                "type": event.event_type,
                "event_type": event.event_type,
                "message": event.title,
                "title": event.title,
                "detail": event.detail,
                "data": event.data,
                "run_id": self.run_id,
                "event_id": event.event_id,
                "seq": event.seq,
                "stage": event.stage,
                "status": event.status,
                "event_schema_version": event.event_schema_version,
                "snapshot_ref": event.snapshot_ref,
                "event_family": event_family or None,
                "event_priority": event_priority or None,
                "event_render_mode": event_render_mode or None,
                "event_index": event_index,
                "replay_importance": replay_importance or None,
                "graph_node_id": graph_node_id or None,
                "scene_ref": scene_ref or None,
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

        if normalized_event.startswith(("browser_", "browser.", "web_", "web.", "brave.", "bing.")):
            return "website"
        if normalized_tool.startswith(("browser.", "marketing.web_research", "web.extract.", "web.dataset.")):
            return "website"

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

        if str(payload.get("event_family") or "").strip().lower() == "api":
            return "api"
        if str(payload.get("plugin_scene_type") or "").strip().lower() == "api":
            return "api"
        if (
            str(payload.get("connector_id") or "").strip()
            or str(payload.get("integration_id") or "").strip()
            or str(payload.get("plugin_connector_id") or "").strip()
        ):
            return "api"

        if normalized_event.startswith(("api_", "api.")):
            return "api"
        if normalized_event.startswith("role_"):
            return "system"
        if normalized_event.startswith(("email_", "email.", "gmail_", "gmail.")):
            return "email"
        if normalized_event.startswith(("sheet_", "sheet.", "sheets.")) or normalized_event == "drive.go_to_sheet":
            return "google_sheets"
        if normalized_event.startswith(("document_", "pdf_", "pdf.")):
            return "document"
        if normalized_event.startswith(("doc_", "doc.", "docs.")) or normalized_event == "drive.go_to_doc":
            provider = str(
                payload.get("provider")
                or payload.get("document_provider")
                or payload.get("workspace_provider")
                or ""
            ).strip().lower()
            if normalized_tool.startswith("workspace.docs."):
                return "google_docs"
            if normalized_tool.startswith("google.api.google_docs"):
                return "google_docs"
            if provider in {"google_docs", "google_workspace"}:
                return "google_docs"
            return "document"
        if normalized_event.startswith("drive."):
            if normalized_tool.startswith("workspace.sheets."):
                return "google_sheets"
            if normalized_tool.startswith("workspace.docs."):
                return "google_docs"
            return "document"

        if normalized_tool.startswith("workspace.docs."):
            return "google_docs"
        if normalized_tool.startswith("docs.create"):
            return "document"
        if normalized_tool.startswith("documents.highlight."):
            return "document"
        if normalized_tool.startswith("workspace.sheets."):
            return "google_sheets"
        if normalized_tool.startswith("workspace.drive."):
            return "document"
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
    def _clean_text(value: Any) -> str:
        return " ".join(str(value or "").split()).strip()

    @staticmethod
    def _string_list(value: Any, *, limit: int = 12) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned = [LiveRunStream._clean_text(item) for item in value]
        return list(dict.fromkeys([item for item in cleaned if item]))[: max(1, int(limit or 1))]

    @staticmethod
    def _is_copy_source_event(*, event_type: str, action: str, payload: dict[str, Any]) -> bool:
        if LiveRunStream._clean_text(payload.get("clipboard_text")):
            return True
        if LiveRunStream._string_list(payload.get("copied_words"), limit=16):
            return True
        if LiveRunStream._string_list(payload.get("copied_snippets"), limit=8):
            return True
        normalized_event = str(event_type or "").strip().lower()
        normalized_action = str(action or "").strip().lower()
        return normalized_action == "extract" and ("copy" in normalized_event or "clipboard" in normalized_event)

    @staticmethod
    def _is_copy_usage_event(*, action: str, payload: dict[str, Any]) -> bool:
        normalized_action = str(action or "").strip().lower()
        if normalized_action != "type":
            return False
        if LiveRunStream._clean_text(payload.get("clipboard_text")):
            return False
        return True

    def _enrich_copy_provenance(
        self,
        *,
        event: AgentActivityEvent,
        payload: dict[str, Any],
        event_index: int,
        graph_node_id: str,
        scene_ref: str,
    ) -> dict[str, Any]:
        data = dict(payload or {})
        action = str(data.get("action") or "").strip().lower()
        scene_surface = str(data.get("scene_surface") or "").strip().lower()
        source_url = (
            self._clean_text(data.get("source_url"))
            or self._clean_text(data.get("url"))
            or self._clean_text(data.get("target_url"))
        )
        snippet = self._clean_text(data.get("clipboard_text"))[:420]
        copied_words = self._string_list(data.get("copied_words"), limit=16)
        copied_snippets = self._string_list(data.get("copied_snippets"), limit=8)
        existing_usage_refs = self._string_list(data.get("copy_usage_refs"), limit=12)

        if self._is_copy_source_event(event_type=event.event_type, action=action, payload=data):
            provenance = {
                "copy_event_ref": event.event_id,
                "copy_event_index": event_index,
                "scene_surface": scene_surface,
                "scene_ref": scene_ref,
                "graph_node_id": graph_node_id,
                "timestamp": event.timestamp,
                "source_url": source_url,
                "snippet": snippet,
                "copied_words": copied_words,
                "copied_snippets": copied_snippets,
            }
            provenance = {key: value for key, value in provenance.items() if value not in (None, "", [])}
            data["copy_provenance"] = provenance
            data["copy_role"] = "source"
            if scene_surface:
                self._latest_copy_by_surface[scene_surface] = provenance
            self._latest_copy_any = provenance
            return data

        if self._is_copy_usage_event(action=action, payload=data):
            source = self._latest_copy_by_surface.get(scene_surface) or self._latest_copy_any
            if isinstance(source, dict) and source:
                copy_ref = self._clean_text(source.get("copy_event_ref"))
                if copy_ref and copy_ref not in existing_usage_refs:
                    existing_usage_refs.append(copy_ref)
                if existing_usage_refs:
                    data["copy_usage_refs"] = existing_usage_refs[:12]
                usage = {
                    "usage_event_ref": event.event_id,
                    "usage_event_index": event_index,
                    "copy_event_ref": copy_ref,
                    "copy_event_index": source.get("copy_event_index"),
                    "scene_surface": source.get("scene_surface"),
                    "scene_ref": source.get("scene_ref"),
                    "graph_node_id": source.get("graph_node_id"),
                    "source_url": source.get("source_url"),
                    "snippet": source.get("snippet"),
                }
                usage = {key: value for key, value in usage.items() if value not in (None, "", [])}
                data["copy_provenance"] = usage
                data["copy_role"] = "usage"
        return data

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
                "browser.",
                "web_",
                "web.",
                "pdf_",
                "pdf.",
                "doc_",
                "doc.",
                "docs.",
                "sheet_",
                "sheet.",
                "sheets.",
                "drive.",
                "email_",
                "email.",
                "gmail_",
                "gmail.",
                "clipboard_",
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
        is_shadow: bool = False,
        activity_event_factory: Callable[..., AgentActivityEvent],
    ) -> Generator[dict[str, Any], None, None]:
        for trace in list(traces or []):
            payload_raw = self._trace_payload(trace)
            if not isinstance(payload_raw, dict):
                continue
            raw_event_type = str(payload_raw.get("event_type") or "tool_progress").strip()
            raw_data = payload_raw.get("data")
            raw_data_dict = dict(raw_data) if isinstance(raw_data, dict) else {}
            raw_data_dict.setdefault("owner_role", resolve_owner_role_for_tool(step.tool_id))
            payload_raw["data"] = raw_data_dict
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
            if is_shadow:
                trace_data_dict["shadow"] = True
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
        is_shadow: bool = False,
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
                is_shadow=is_shadow,
                activity_event_factory=activity_event_factory,
            ):
                yield trace_event
