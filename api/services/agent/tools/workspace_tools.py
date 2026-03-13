from __future__ import annotations

# Deprecated shim: moved to `api/services/agent/tools/workspace/`.
from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.workspace import (
    WorkspaceDocsReadTool as _WorkspaceDocsReadTool,
    WorkspaceDocsTemplateTool as _WorkspaceDocsTemplateTool,
    WorkspaceDriveDeleteTool as _WorkspaceDriveDeleteTool,
    WorkspaceDriveRenameTool as _WorkspaceDriveRenameTool,
    WorkspaceDriveSearchTool as _WorkspaceDriveSearchTool,
    WorkspaceResearchNotesTool as _WorkspaceResearchNotesTool,
    WorkspaceSheetsAppendTool as _WorkspaceSheetsAppendTool,
    WorkspaceSheetsReadTool as _WorkspaceSheetsReadTool,
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


class WorkspaceSheetsReadTool(_WorkspaceSheetsReadTool):
    def _connector_registry(self):
        return get_connector_registry()


class WorkspaceDocsReadTool(_WorkspaceDocsReadTool):
    def _connector_registry(self):
        return get_connector_registry()


class WorkspaceDriveDeleteTool(_WorkspaceDriveDeleteTool):
    def _connector_registry(self):
        return get_connector_registry()


class WorkspaceDriveRenameTool(_WorkspaceDriveRenameTool):
    def _connector_registry(self):
        return get_connector_registry()


__all__ = [
    "_now_iso",
    "_chunk_text",
    "_sheet_col_name",
    "WorkspaceDocsReadTool",
    "WorkspaceDocsTemplateTool",
    "WorkspaceDriveDeleteTool",
    "WorkspaceDriveRenameTool",
    "WorkspaceDriveSearchTool",
    "WorkspaceResearchNotesTool",
    "WorkspaceSheetsAppendTool",
    "WorkspaceSheetsReadTool",
    "WorkspaceSheetsTrackStepTool",
]
