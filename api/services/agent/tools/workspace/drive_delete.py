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


def _extract_file_id(raw: str) -> str:
    """Extract a Drive file ID from a URL or return the string as-is."""
    raw = raw.strip()
    for marker in ("/d/", "id=", "/file/d/", "folders/"):
        if marker in raw:
            after = raw.split(marker)[1]
            fid = after.split("/")[0].split("?")[0].split("&")[0].strip()
            if fid:
                return fid
    return raw


class WorkspaceDriveDeleteTool(WorkspaceConnectorTool):
    metadata = ToolMetadata(
        tool_id="workspace.drive.delete",
        action_class="execute",
        risk_level="high",
        required_permissions=["drive.write"],
        execution_policy="confirm_before_execute",
        description="Permanently delete a file from Google Drive. Irreversible.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        raw_id = str(params.get("file_id") or params.get("document_id") or params.get("spreadsheet_id") or "").strip()

        # Accept a URL as input
        if not raw_id:
            for key in ("file_url", "document_url", "spreadsheet_url", "url", "link"):
                url_val = str(params.get(key) or "").strip()
                if url_val:
                    raw_id = _extract_file_id(url_val)
                    if raw_id:
                        break

        if not raw_id:
            raise ToolExecutionError(
                "`file_id` is required. Provide the Drive file ID or a Google Drive/Docs/Sheets URL."
            )

        file_id = _extract_file_id(raw_id)
        if not file_id:
            raise ToolExecutionError(f"Could not parse a valid file ID from: {raw_id!r}")

        connector = self._workspace_connector(settings=context.settings)
        connector.delete_drive_file(file_id=file_id)

        events = [
            ToolTraceEvent(
                event_type="drive.delete_completed",
                title="Drive file deleted",
                detail=file_id,
                data=scene_payload(
                    surface="google_drive",
                    lane="drive-delete",
                    payload={"file_id": file_id, "deleted": True},
                ),
            ),
        ]

        return ToolExecutionResult(
            summary=f"Deleted Drive file {file_id}.",
            content=f"File `{file_id}` has been permanently deleted from Google Drive.",
            data={"file_id": file_id, "deleted": True},
            sources=[],
            next_steps=[],
            events=events,
        )


class WorkspaceDriveRenameTool(WorkspaceConnectorTool):
    metadata = ToolMetadata(
        tool_id="workspace.drive.rename",
        action_class="execute",
        risk_level="medium",
        required_permissions=["drive.write"],
        execution_policy="auto_execute",
        description="Rename a Google Drive file (Docs, Sheets, or any Drive file).",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        raw_id = str(params.get("file_id") or params.get("document_id") or params.get("spreadsheet_id") or "").strip()
        name = str(params.get("name") or params.get("title") or "").strip()

        if not raw_id:
            for key in ("file_url", "document_url", "spreadsheet_url", "url"):
                url_val = str(params.get(key) or "").strip()
                if url_val:
                    raw_id = _extract_file_id(url_val)
                    if raw_id:
                        break

        if not raw_id:
            raise ToolExecutionError("`file_id` is required.")
        if not name:
            raise ToolExecutionError("`name` (new filename) is required.")

        file_id = _extract_file_id(raw_id)
        connector = self._workspace_connector(settings=context.settings)
        connector.rename_drive_file(file_id=file_id, name=name)

        events = [
            ToolTraceEvent(
                event_type="drive.rename_completed",
                title="Drive file renamed",
                detail=f"{file_id} → {name}",
                data=scene_payload(
                    surface="google_drive",
                    lane="drive-rename",
                    payload={"file_id": file_id, "name": name},
                ),
            ),
        ]

        return ToolExecutionResult(
            summary=f'Renamed Drive file to "{name}".',
            content=f"File `{file_id}` renamed to \"{name}\".",
            data={"file_id": file_id, "name": name},
            sources=[],
            next_steps=[],
            events=events,
        )
