"""Maia SDK — the collaboration and observability layer for AI agents.

One import, everything you need.

Quick start:

    from maia_sdk import ACPClient, message, handoff, review

    # Create a client
    client = ACPClient(agent_id="agent://researcher")

    # Connect to a live stream
    client.connect("http://localhost:8000/acp/events")

    # Listen for messages
    @client.on("message")
    def handle(event):
        msg = event.as_message()
        print(f"{msg.from_agent}: {msg.content}")

    # Send a message
    msg = message(
        from_agent="agent://researcher",
        to="agent://analyst",
        intent="challenge",
        content="Can you verify the revenue figures?",
    )

Framework adapters:

    from maia_sdk.adapters import langchain, crewai, autogen
"""

__version__ = "0.1.0"

# ── Re-export everything from maia-acp ────────────────────────────────────────
from maia_acp import (
    # Types
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
    # Builders
    envelope,
    message,
    handoff,
    review,
    artifact,
    activity,
    capabilities,
    # Client
    ACPClient,
    # Stream
    parse_sse_line,
    stream_events,
    connect_sse,
)

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
    # Stream
    "parse_sse_line",
    "stream_events",
    "connect_sse",
]
