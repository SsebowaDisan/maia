from __future__ import annotations

# Deprecated shim: moved to `api/services/agent/tools/workspace/`.
from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.workspace import (
    WorkspaceDocsTemplateTool as _WorkspaceDocsTemplateTool,
    WorkspaceDriveSearchTool as _WorkspaceDriveSearchTool,
    WorkspaceResearchNotesTool as _WorkspaceResearchNotesTool,
    WorkspaceSheetsAppendTool as _WorkspaceSheetsAppendTool,
    WorkspaceSheetsTrackStepTool as _WorkspaceSheetsTrackStepTool,
)
from api.services.agent.tools.workspace.common import (
    chunk_text as _chunk_text,
    now_iso as _now_iso,
    sheet_col_name as _sheet_col_name,
)


class WorkspaceDriveSearchTool(_WorkspaceDriveSearchTool):
    def _connector_registry(self):
        return get_connector_registry()


class WorkspaceSheetsAppendTool(_WorkspaceSheetsAppendTool):
    def _connector_registry(self):
        return get_connector_registry()


class WorkspaceDocsTemplateTool(_WorkspaceDocsTemplateTool):
    def _connector_registry(self):
        return get_connector_registry()


class WorkspaceResearchNotesTool(_WorkspaceResearchNotesTool):
    def _connector_registry(self):
        return get_connector_registry()


class WorkspaceSheetsTrackStepTool(_WorkspaceSheetsTrackStepTool):
    def _connector_registry(self):
        return get_connector_registry()


__all__ = [
    "_now_iso",
    "_chunk_text",
    "_sheet_col_name",
    "WorkspaceDriveSearchTool",
    "WorkspaceSheetsAppendTool",
    "WorkspaceDocsTemplateTool",
    "WorkspaceResearchNotesTool",
    "WorkspaceSheetsTrackStepTool",
]
