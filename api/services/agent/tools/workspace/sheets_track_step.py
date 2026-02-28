from __future__ import annotations

from typing import Any

from api.services.agent.models import AgentSource
from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionResult, ToolMetadata, ToolTraceEvent

from .base import WorkspaceConnectorTool
from .common import drain_stream, now_iso, sheet_col_name


class WorkspaceSheetsTrackStepTool(WorkspaceConnectorTool):
    metadata = ToolMetadata(
        tool_id="workspace.sheets.track_step",
        action_class="execute",
        risk_level="medium",
        required_permissions=["sheets.write"],
        execution_policy="auto_execute",
        description="Track deep research step progress in a Google Sheet.",
    )

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ):
        step_name = str(params.get("step_name") or prompt).strip() or "Unnamed step"
        status = str(params.get("status") or "completed").strip() or "completed"
        detail = str(params.get("detail") or "").strip()
        source_url = str(params.get("source_url") or "").strip()
        title = str(params.get("title") or "").strip() or f"Maia Deep Research Tracker {context.run_id[:8]}"
        sheet_name = str(params.get("sheet_name") or "Tracker").strip() or "Tracker"
        sheet_range = f"{sheet_name}!A1"
        connector = self._workspace_connector(settings=context.settings)

        spreadsheet_id = str(context.settings.get("__deep_research_sheet_id") or "").strip()
        spreadsheet_url = str(context.settings.get("__deep_research_sheet_url") or "").strip()
        trace_events: list[ToolTraceEvent] = []
        open_event = ToolTraceEvent(
            event_type="sheet_open",
            title="Open Google Sheets tracker",
            detail=spreadsheet_url or spreadsheet_id or title,
            data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
        )
        trace_events.append(open_event)
        yield open_event

        header_written = bool(context.settings.get("__deep_research_sheet_header_written"))
        created_now = False
        if not spreadsheet_id:
            create_event = ToolTraceEvent(
                event_type="sheet_open",
                title="Create Google Sheets tracker",
                detail=title,
                data={"spreadsheet_id": "", "spreadsheet_url": ""},
            )
            trace_events.append(create_event)
            yield create_event
            sheet_create_started = ToolTraceEvent(
                event_type="sheets.create_started",
                title="Start Google Sheets tracker creation",
                detail=title,
                data={"title": title, "sheet_title": sheet_name},
            )
            trace_events.append(sheet_create_started)
            yield sheet_create_started
            created = connector.create_spreadsheet(title=title, sheet_title=sheet_name)
            spreadsheet_id = str(created.get("spreadsheet_id") or "").strip()
            spreadsheet_url = str(created.get("spreadsheet_url") or "").strip()
            context.settings["__deep_research_sheet_id"] = spreadsheet_id
            context.settings["__deep_research_sheet_url"] = spreadsheet_url
            context.settings["__deep_research_sheet_range"] = sheet_range
            header_written = False
            created_now = True
            sheet_create_completed = ToolTraceEvent(
                event_type="sheets.create_completed",
                title="Google Sheets tracker created",
                detail=spreadsheet_id or title,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": spreadsheet_url,
                    "source_url": spreadsheet_url,
                },
            )
            trace_events.append(sheet_create_completed)
            yield sheet_create_completed
            if spreadsheet_url:
                open_sheet_event = ToolTraceEvent(
                    event_type="drive.go_to_sheet",
                    title="Open tracker sheet link",
                    detail=spreadsheet_url,
                    data={"source_url": spreadsheet_url, "spreadsheet_url": spreadsheet_url},
                )
                trace_events.append(open_sheet_event)
                yield open_sheet_event

        if spreadsheet_id and not header_written:
            header_start = ToolTraceEvent(
                event_type="sheets.append_started",
                title="Write tracker header row",
                detail=sheet_range,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "range": sheet_range,
                    "rows": 1,
                    "source_url": spreadsheet_url,
                },
            )
            trace_events.append(header_start)
            yield header_start
            connector.append_sheet_values(
                spreadsheet_id=spreadsheet_id,
                sheet_range=sheet_range,
                values=[["timestamp", "run_id", "step", "status", "detail", "source_url"]],
            )
            header_done = ToolTraceEvent(
                event_type="sheets.append_completed",
                title="Tracker header row saved",
                detail=sheet_range,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "range": sheet_range,
                    "updated_rows": 1,
                    "source_url": spreadsheet_url,
                },
            )
            trace_events.append(header_done)
            yield header_done
            context.settings["__deep_research_sheet_header_written"] = True

        row_values = [now_iso(), context.run_id, step_name, status, detail, source_url]
        for cell_index, cell_value in enumerate(row_values):
            cell_event = ToolTraceEvent(
                event_type="sheet_cell_update",
                title=f"Update cell {sheet_col_name(cell_index)}",
                detail=str(cell_value)[:140],
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "column": sheet_col_name(cell_index),
                    "value": str(cell_value),
                },
            )
            trace_events.append(cell_event)
            yield cell_event

        append_event = ToolTraceEvent(
            event_type="sheet_append_row",
            title="Append tracker row",
            detail=f"{step_name} ({status})",
            data={"spreadsheet_id": spreadsheet_id, "sheet_range": sheet_range},
        )
        trace_events.append(append_event)
        yield append_event
        append_started = ToolTraceEvent(
            event_type="sheets.append_started",
            title="Start appending tracker row",
            detail=f"{step_name} ({status})",
            data={
                "spreadsheet_id": spreadsheet_id,
                "range": sheet_range,
                "rows": 1,
                "source_url": spreadsheet_url,
            },
        )
        trace_events.append(append_started)
        yield append_started

        response = (
            connector.append_sheet_values(
                spreadsheet_id=spreadsheet_id,
                sheet_range=sheet_range,
                values=[row_values],
            )
            if spreadsheet_id
            else {}
        )
        updated_rows = (
            (response.get("updates") or {}).get("updatedRows")
            if isinstance(response, dict)
            else 0
        )
        append_completed = ToolTraceEvent(
            event_type="sheets.append_completed",
            title="Tracker row appended",
            detail=f"Updated rows: {updated_rows or 0}",
            data={
                "spreadsheet_id": spreadsheet_id,
                "range": sheet_range,
                "updated_rows": updated_rows or 0,
                "source_url": spreadsheet_url,
            },
        )
        trace_events.append(append_completed)
        yield append_completed
        save_event = ToolTraceEvent(
            event_type="sheet_save",
            title="Save tracker updates",
            detail=spreadsheet_id or "tracker saved",
            data={
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet_url": spreadsheet_url,
                "source_url": spreadsheet_url,
            },
        )
        trace_events.append(save_event)
        yield save_event

        return ToolExecutionResult(
            summary=f"Tracked step `{step_name}` in Google Sheets.",
            content="\n".join(
                [
                    f"Spreadsheet ID: {spreadsheet_id or 'unknown'}",
                    f"Spreadsheet URL: {spreadsheet_url or 'not available'}",
                    f"Step: {step_name}",
                    f"Status: {status}",
                    f"Updated rows: {updated_rows or 0}",
                ]
            ),
            data={
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet_url": spreadsheet_url,
                "updated_rows": updated_rows or 0,
                "step_name": step_name,
                "status": status,
                "created_now": created_now,
            },
            sources=[
                AgentSource(
                    source_type="web",
                    label=f"{title} ({sheet_name})",
                    url=spreadsheet_url or None,
                    score=0.7 if spreadsheet_url else 0.45,
                    metadata={"provider": "google_sheets", "spreadsheet_id": spreadsheet_id},
                )
            ]
            if spreadsheet_id
            else [],
            next_steps=["Continue marking each completed action in the tracker."],
            events=trace_events,
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        return drain_stream(self.execute_stream(context=context, prompt=prompt, params=params))
