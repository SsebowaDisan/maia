from __future__ import annotations

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import AgentTool


class WorkspaceConnectorTool(AgentTool):
    def _connector_registry(self):
        return get_connector_registry()

    def _workspace_connector(self, *, settings: dict[str, object]):
        return self._connector_registry().build("google_workspace", settings=settings)
