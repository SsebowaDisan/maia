from __future__ import annotations

from typing import Any

from api.services.agent.models import AgentSource
from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionResult, ToolMetadata, ToolTraceEvent

from .base import WorkspaceConnectorTool


class WorkspaceDriveSearchTool(WorkspaceConnectorTool):
    metadata = ToolMetadata(
        tool_id="workspace.drive.search",
        action_class="read",
        risk_level="low",
        required_permissions=["drive.read"],
        execution_policy="auto_execute",
        description="Search Google Drive files for workflow context.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        query = str(params.get("query") or prompt).strip()
        connector = self._workspace_connector(settings=context.settings)
        response = connector.list_drive_files(query=query)
        files = response.get("files") if isinstance(response, dict) else []
        if not isinstance(files, list):
            files = []

        lines = [f"### Google Drive results ({len(files)})"]
        sources: list[AgentSource] = []
        for row in files[:12]:
            if not isinstance(row, dict):
                continue
            file_id = str(row.get("id") or "")
            name = str(row.get("name") or "Drive file")
            mime_type = str(row.get("mimeType") or "")
            drive_url = f"https://drive.google.com/file/d/{file_id}/view" if file_id else ""
            lines.append(f"- {name} ({mime_type or 'unknown'})")
            sources.append(
                AgentSource(
                    source_type="web",
                    label=name,
                    url=drive_url or None,
                    score=0.65,
                    metadata={"provider": "google_drive", "file_id": file_id},
                )
            )
        if len(lines) == 1:
            lines.append("- No files found.")

        return ToolExecutionResult(
            summary=f"Found {len(files)} Drive file(s).",
            content="\n".join(lines),
            data={"query": query, "count": len(files)},
            sources=sources,
            next_steps=["Open selected files and connect them to report generation."],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Search Google Drive",
                    detail=query or "recent files",
                    data={"count": len(files)},
                )
            ],
        )
