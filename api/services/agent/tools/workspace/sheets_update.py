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
from .common import scene_payload
from ..google_target_resolution import resolve_sheet_reference


class WorkspaceSheetsUpdateTool(WorkspaceConnectorTool):
    metadata = ToolMetadata(
        tool_id="workspace.sheets.update",
        action_class="execute",
        risk_level="high",
        required_permissions=["sheets.write"],
        execution_policy="confirm_before_execute",
        description="Overwrite a specific cell range in Google Sheets (PUT semantics).",
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

        response = connector.update_sheet_range(
            spreadsheet_id=spreadsheet_id,
            sheet_range=sheet_range,
            values=values,
        )

        events = [
            ToolTraceEvent(
                event_type="sheet_open",
                title="Open Google Sheet",
                detail=spreadsheet_id,
                data=scene_payload(
                    surface="google_sheets",
                    lane="sheet-open",
                    payload={
                        "spreadsheet_id": spreadsheet_id,
                        "spreadsheet_url": spreadsheet_url,
                        "source_url": spreadsheet_url,
                    },
                ),
            ),
            ToolTraceEvent(
                event_type="sheets.update_started",
                title="Start updating range",
                detail=f"{sheet_range} ({len(values)} rows)",
                data=scene_payload(
                    surface="google_sheets",
                    lane="sheet-update-start",
                    payload={
                        "spreadsheet_id": spreadsheet_id,
                        "range": sheet_range,
                        "rows": len(values),
                        "source_url": spreadsheet_url,
                    },
                ),
            ),
            ToolTraceEvent(
                event_type="sheets.update_completed",
                title="Range updated",
                detail=f"{sheet_range} — {len(values)} row(s) written",
                data=scene_payload(
                    surface="google_sheets",
                    lane="sheet-update-done",
                    payload={
                        "spreadsheet_id": spreadsheet_id,
                        "range": sheet_range,
                        "rows": len(values),
                        "source_url": spreadsheet_url,
                    },
                ),
            ),
            ToolTraceEvent(
                event_type="sheet_save",
                title="Save Google Sheet",
                detail=spreadsheet_id,
                data=scene_payload(
                    surface="google_sheets",
                    lane="sheet-save",
                    payload={
                        "spreadsheet_id": spreadsheet_id,
                        "spreadsheet_url": spreadsheet_url,
                        "source_url": spreadsheet_url,
                    },
                ),
            ),
        ]

        return ToolExecutionResult(
            summary=f"Updated range {sheet_range} in Google Sheet ({len(values)} row(s) written).",
            content=(
                f"Range `{sheet_range}` in spreadsheet `{spreadsheet_id}` overwritten.\n"
                f"- Rows written: {len(values)}"
            ),
            data={
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet_url": spreadsheet_url,
                "sheet_range": sheet_range,
                "rows_written": len(values),
                "update_info": response.get("update_info") or {},
            },
            sources=[],
            next_steps=["Verify updated cells and apply formatting rules if needed."],
            events=events,
        )
