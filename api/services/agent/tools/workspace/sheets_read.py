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
from .common import scene_payload, sheet_col_name
from ..google_target_resolution import resolve_sheet_reference


class WorkspaceSheetsReadTool(WorkspaceConnectorTool):
    metadata = ToolMetadata(
        tool_id="workspace.sheets.read",
        action_class="read",
        risk_level="low",
        required_permissions=["sheets.read"],
        execution_policy="auto_execute",
        description="Read a range of cells from a Google Sheet and return the values.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        spreadsheet_id = str(params.get("spreadsheet_id") or "").strip()
        sheet_range = str(params.get("sheet_range") or "Sheet1!A1:Z100").strip()

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

        spreadsheet_url = (
            str(resolved_ref.canonical_url).strip()
            if resolved_ref is not None and str(resolved_ref.canonical_url).strip()
            else f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        )

        connector = self._workspace_connector(settings=context.settings)
        response = connector.read_sheet_range(
            spreadsheet_id=spreadsheet_id,
            sheet_range=sheet_range,
        )

        values: list[list[Any]] = response.get("values") or []
        row_count = len(values)
        col_count = max((len(r) for r in values), default=0)

        # Build a readable text table for the content summary
        header = values[0] if values else []
        preview_lines: list[str] = []
        for i, row in enumerate(values[:20]):
            row_str = " | ".join(str(cell) for cell in row)
            preview_lines.append(f"Row {i + 1}: {row_str}")
        preview_text = "\n".join(preview_lines)
        if row_count > 20:
            preview_text += f"\n... ({row_count - 20} more rows)"

        col_label = sheet_col_name(col_count - 1) if col_count > 0 else "A"

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
                event_type="sheets.read_completed",
                title="Sheet range read",
                detail=f"{sheet_range} — {row_count} rows × {col_count} columns",
                data=scene_payload(
                    surface="google_sheets",
                    lane="sheet-read-done",
                    payload={
                        "spreadsheet_id": spreadsheet_id,
                        "sheet_range": sheet_range,
                        "rows": row_count,
                        "columns": col_count,
                        "source_url": spreadsheet_url,
                    },
                ),
            ),
        ]

        return ToolExecutionResult(
            summary=f"Read {row_count} row(s) × {col_count} column(s) from {sheet_range}.",
            content=preview_text or "(empty range)",
            data={
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet_url": spreadsheet_url,
                "sheet_range": sheet_range,
                "values": values,
                "row_count": row_count,
                "column_count": col_count,
                "headers": header,
            },
            sources=[],
            next_steps=[
                f"Use workspace.sheets.append to add rows based on the data read from {sheet_range}."
            ],
            events=events,
        )
