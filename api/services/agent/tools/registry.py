from __future__ import annotations

from typing import Any, Generator

from api.services.agent.audit import get_audit_logger
from api.services.agent.governance import get_governance_service
from api.services.agent.policy import (
    ACCESS_MODE_FULL,
    ACTION_CLASS_EXECUTE,
    AgentAccessContext,
    AgentToolCapability,
    get_capability_matrix,
    has_required_role,
    resolve_execution_policy,
)
from api.services.agent.tools.ads_tools import GoogleAdsPerformanceTool
from api.services.agent.tools.analytics_tools import GA4ReportTool
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
)
from api.services.agent.tools.browser_tools import PlaywrightInspectTool
from api.services.agent.tools.calendar_tools import CalendarCreateEventTool
from api.services.agent.tools.charts_tools import ChartGenerateTool
from api.services.agent.tools.contact_form_tools import BrowserContactFormSendTool
from api.services.agent.tools.data_tools import DataAnalysisTool, ReportGenerationTool
from api.services.agent.tools.discovery_tools import LocalDiscoveryTool
from api.services.agent.tools.document_tools import DocumentCreateTool
from api.services.agent.tools.document_highlight_tools import DocumentHighlightExtractTool
from api.services.agent.tools.email_tools import EmailDraftTool, EmailSendTool
from api.services.agent.tools.gmail_tools import GmailDraftTool, GmailSearchTool, GmailSendTool
from api.services.agent.tools.invoice_tools import InvoiceCreateTool, InvoiceSendTool
from api.services.agent.tools.maps_tools import MapsDistanceTool, MapsGeocodeTool
from api.services.agent.tools.research_tools import CompetitorProfileTool, WebResearchTool
from api.services.agent.tools.validation_tools import EmailValidationTool
from api.services.agent.tools.workplace_tools import SlackPostMessageTool
from api.services.agent.tools.workspace_tools import (
    WorkspaceDocsTemplateTool,
    WorkspaceDriveSearchTool,
    WorkspaceResearchNotesTool,
    WorkspaceSheetsTrackStepTool,
    WorkspaceSheetsAppendTool,
)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}
        self._capabilities: dict[str, AgentToolCapability] = {
            capability.tool_id: capability for capability in get_capability_matrix()
        }
        self.register(WebResearchTool())
        self.register(CompetitorProfileTool())
        self.register(EmailDraftTool())
        self.register(EmailSendTool())
        self.register(GoogleAdsPerformanceTool())
        self.register(DataAnalysisTool())
        self.register(DocumentHighlightExtractTool())
        self.register(ReportGenerationTool())
        self.register(DocumentCreateTool())
        self.register(WorkspaceDocsTemplateTool())
        self.register(WorkspaceResearchNotesTool())
        self.register(WorkspaceSheetsTrackStepTool())
        self.register(WorkspaceDriveSearchTool())
        self.register(WorkspaceSheetsAppendTool())
        self.register(InvoiceCreateTool())
        self.register(InvoiceSendTool())
        self.register(SlackPostMessageTool())
        self.register(LocalDiscoveryTool())
        self.register(PlaywrightInspectTool())
        self.register(BrowserContactFormSendTool())
        self.register(GmailDraftTool())
        self.register(GmailSendTool())
        self.register(GmailSearchTool())
        self.register(CalendarCreateEventTool())
        self.register(GA4ReportTool())
        self.register(ChartGenerateTool())
        self.register(EmailValidationTool())
        self.register(MapsGeocodeTool())
        self.register(MapsDistanceTool())

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.metadata.tool_id] = tool

    def list_tools(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for tool_id in sorted(self._tools.keys()):
            tool = self._tools[tool_id]
            capability = self._capabilities.get(tool_id)
            output.append(
                {
                    "tool_id": tool.metadata.tool_id,
                    "action_class": tool.metadata.action_class,
                    "risk_level": tool.metadata.risk_level,
                    "required_permissions": tool.metadata.required_permissions,
                    "execution_policy": tool.metadata.execution_policy,
                    "description": tool.metadata.description,
                    "minimum_role": capability.minimum_role if capability else "member",
                    "domain": capability.domain if capability else "unknown",
                }
            )
        return output

    def get(self, tool_id: str) -> AgentTool:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise KeyError(f"Unknown tool: {tool_id}")
        return tool

    def execute(
        self,
        *,
        tool_id: str,
        context: ToolExecutionContext,
        access: AgentAccessContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        stream = self.execute_with_trace(
            tool_id=tool_id,
            context=context,
            access=access,
            prompt=prompt,
            params=params,
        )
        trace_events: list[ToolTraceEvent] = []
        while True:
            try:
                trace = next(stream)
            except StopIteration as stop:
                result = stop.value
                break
            trace_events.append(trace)

        if trace_events:
            result.events = trace_events
        return result

    def execute_with_trace(
        self,
        *,
        tool_id: str,
        context: ToolExecutionContext,
        access: AgentAccessContext,
        prompt: str,
        params: dict[str, Any],
    ) -> Generator[ToolTraceEvent, None, ToolExecutionResult]:
        tool, capability, effective_policy = self._prepare_execution(
            tool_id=tool_id,
            access=access,
            params=params,
        )
        result = yield from tool.execute_stream(context=context, prompt=prompt, params=params)
        get_audit_logger().write(
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            event="tool_executed",
            payload={
                "tool_id": tool_id,
                "action_class": capability.action_class,
                "effective_policy": effective_policy,
                "summary": result.summary,
            },
        )
        return result

    def _prepare_execution(
        self,
        *,
        tool_id: str,
        access: AgentAccessContext,
        params: dict[str, Any],
    ) -> tuple[AgentTool, AgentToolCapability, str]:
        tool = self.get(tool_id)
        if not get_governance_service().is_tool_enabled(tool_id):
            raise ToolExecutionError(f"Tool `{tool_id}` is disabled by governance policy.")

        capability = self._capabilities.get(tool_id)
        if capability is None:
            raise ToolExecutionError(f"Capability mapping missing for tool: {tool_id}")
        if not has_required_role(access, capability.minimum_role):
            full_access_override = (
                access.access_mode == ACCESS_MODE_FULL and access.full_access_enabled
            )
            if not full_access_override:
                raise ToolExecutionError(
                    f"Role `{access.role}` does not meet required role `{capability.minimum_role}`."
                )

        effective_policy = resolve_execution_policy(capability, access)
        if (
            capability.action_class == ACTION_CLASS_EXECUTE
            and effective_policy == "confirm_before_execute"
            and not bool(params.get("confirmed", False))
        ):
            raise ToolExecutionError(
                f"Tool `{tool_id}` requires confirmation in restricted mode."
            )

        return tool, capability, effective_policy


_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
