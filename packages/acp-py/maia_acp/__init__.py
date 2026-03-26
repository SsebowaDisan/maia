"""maia-acp — Agent Collaboration Protocol for Python.

Quick start:

    from maia_acp import ACPClient, message

    client = ACPClient(agent_id="agent://my-agent")
    client.connect("http://localhost:8000/acp/events")

    @client.on("message")
    def handle(event):
        print(f"{event.payload.from_agent}: {event.payload.content}")
"""

from maia_acp.types import (
    ACPEvent,
    ACPMessage,
    ACPHandoff,
    ACPReview,
    ACPArtifact,
    ACPActivity,
    ACPCapabilities,
    HandoffTask,
    ReviewIssue,
    AgentPersonality,
    AgentSkill,
    ToolActivity,
    BrowserActivity,
    ProgressInfo,
    CostInfo,
    AgentPresence,
)
from maia_acp.builders import (
    envelope,
    message,
    handoff,
    review,
    artifact,
    activity,
    capabilities,
)
from maia_acp.client import ACPClient
from maia_acp.registry import ACPAgentRegistry
from maia_acp.stream import parse_sse_line, stream_events, connect_sse

__version__ = "0.1.0"
__all__ = [
    # Types
    "ACPEvent",
    "ACPMessage",
    "ACPHandoff",
    "ACPReview",
    "ACPArtifact",
    "ACPActivity",
    "ACPCapabilities",
    "HandoffTask",
    "ReviewIssue",
    "AgentPersonality",
    "AgentSkill",
    "ToolActivity",
    "BrowserActivity",
    "ProgressInfo",
    "CostInfo",
    "AgentPresence",
    # Builders
    "envelope",
    "message",
    "handoff",
    "review",
    "artifact",
    "activity",
    "capabilities",
    # Client
    "ACPClient",
    "ACPAgentRegistry",
    # Stream
    "parse_sse_line",
    "stream_events",
    "connect_sse",
]
