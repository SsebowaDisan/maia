from __future__ import annotations

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)


class SlackPostMessageTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="slack.post_message",
        action_class="execute",
        risk_level="high",
        required_permissions=["slack.write"],
        execution_policy="confirm_before_execute",
        description="Post a message in Slack channel.",
    )

    def execute(self, *, context: ToolExecutionContext, prompt: str, params: dict) -> ToolExecutionResult:
        channel = str(params.get("channel") or "").strip()
        text = str(params.get("text") or prompt).strip()
        if not channel:
            return ToolExecutionResult(
                summary="Slack channel missing, post skipped.",
                content="Set `channel` in params to deliver Slack message.",
                data={"status": "skipped"},
                sources=[],
                next_steps=["Provide Slack channel and rerun."],
                events=[
                    ToolTraceEvent(
                        event_type="approval_required",
                        title="Slack channel required",
                        detail="Provide a target Slack channel before posting.",
                    )
                ],
            )

        connector = get_connector_registry().build("slack", settings=context.settings)
        response = connector.post_message(channel=channel, text=text)
        return ToolExecutionResult(
            summary=f"Posted Slack message to {channel}.",
            content=f"Slack message delivered to {channel}.",
            data=response,
            sources=[],
            next_steps=["Track thread replies for follow-up actions."],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Prepare Slack payload",
                    detail=f"Channel: {channel}",
                    data={"channel": channel},
                ),
                ToolTraceEvent(
                    event_type="tool_completed",
                    title="Slack message sent",
                    detail=f"Posted update to {channel}",
                    data={"channel": channel},
                ),
            ],
        )
