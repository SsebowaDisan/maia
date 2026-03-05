from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import (
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)

from .base import WorkspaceConnectorTool
from ..google_target_resolution import resolve_sheet_reference


class WorkspaceSheetsAppendTool(WorkspaceConnectorTool):
    metadata = ToolMetadata(
        tool_id="workspace.sheets.append",
        action_class="execute",
        risk_level="high",
        required_permissions=["sheets.write"],
        execution_policy="confirm_before_execute",
        description="Append rows to Google Sheets for CRM/analytics tracking.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        spreadsheet_id = str(params.get("spreadsheet_id") or "").strip()
        sheet_range = str(params.get("sheet_range") or "Sheet1!A1").strip()
        values = params.get("values")
        resolved_ref = None
        if not spreadsheet_id:
            resolved_ref = resolve_sheet_reference(
                prompt=prompt,
                params=params,
                settings=context.settings,
            )
            if resolved_ref is not None:
                spreadsheet_id = resolved_ref.resource_id
        if not spreadsheet_id:
            raise ToolExecutionError(
                "`spreadsheet_id` is required. Provide spreadsheet_id, a Google Sheets link, or a saved alias."
            )
        if not isinstance(values, list) or not values:
            raise ToolExecutionError("`values` must be a non-empty 2D array.")

        connector = self._workspace_connector(settings=context.settings)
        spreadsheet_url = (
            str(resolved_ref.canonical_url).strip()
            if resolved_ref is not None and str(resolved_ref.canonical_url).strip()
            else f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        )
        response = connector.append_sheet_values(
            spreadsheet_id=spreadsheet_id,
            sheet_range=sheet_range,
            values=values,
        )
        updated_rows = (
            (response.get("updates") or {}).get("updatedRows")
            if isinstance(response, dict)
            else 0
        )
        events = [
            ToolTraceEvent(
                event_type="sheet_open",
                title="Open Google Sheet",
                detail=spreadsheet_id,
                data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
            ),
            ToolTraceEvent(
                event_type="sheets.append_started",
                title="Start appending rows",
                detail=f"{sheet_range} ({len(values)} rows)",
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "range": sheet_range,
                    "rows": len(values),
                    "source_url": spreadsheet_url,
                },
            ),
            ToolTraceEvent(
                event_type="sheet_append_row",
                title="Append row payload",
                detail=f"{len(values)} row(s)",
                data={"spreadsheet_id": spreadsheet_id, "sheet_range": sheet_range},
            ),
            ToolTraceEvent(
                event_type="sheets.append_completed",
                title="Rows appended",
                detail=f"Updated rows: {updated_rows or 0}",
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "range": sheet_range,
                    "updated_rows": updated_rows or 0,
                    "source_url": spreadsheet_url,
                },
            ),
            ToolTraceEvent(
                event_type="sheet_save",
                title="Save Google Sheet",
                detail=spreadsheet_id,
                data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
            ),
        ]

        return ToolExecutionResult(
            summary=f"Appended rows to Google Sheet ({updated_rows or 0} updated).",
            content=(
                f"Rows appended to spreadsheet `{spreadsheet_id}` at range `{sheet_range}`.\n"
                f"- Updated rows: {updated_rows or 0}"
            ),
            data={
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet_url": spreadsheet_url,
                "sheet_range": sheet_range,
                "updated_rows": updated_rows,
            },
            sources=[],
            next_steps=["Verify appended rows and apply formatting rules if needed."],
            events=events,
        )
