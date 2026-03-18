"""Adapters that wrap filesystem tool classes as AgentTool instances."""
from __future__ import annotations

from typing import Any, Generator

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.filesystem.tools import (
    FileEditTool,
    FileListTool,
    FileReadTool,
    FileSearchTool,
    FileWriteTool,
)


class _FilesystemToolAdapter(AgentTool):
    """Bridge between the filesystem tool execute(params, settings) protocol
    and the AgentTool execute(*, context, prompt, params) protocol."""

    def __init__(
        self,
        inner: Any,
        metadata: ToolMetadata,
    ) -> None:
        self._inner = inner
        self.metadata = metadata

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        settings = dict(context.settings)
        events: list[ToolTraceEvent] = []
        content_parts: list[str] = []
        had_error = False

        for chunk in self._inner.execute(params, settings):
            ctype = chunk.get("type", "")
            body = chunk.get("content", "")
            if ctype == "error":
                had_error = True
                content_parts.append(f"[error] {body}")
            else:
                content_parts.append(body)

        content = "\n".join(content_parts) if content_parts else "(no output)"
        summary = content[:200] if not had_error else f"Error: {content[:200]}"

        return ToolExecutionResult(
            summary=summary,
            content=content,
            data={},
            sources=[],
            next_steps=[],
            events=events,
        )


# ---------------------------------------------------------------------------
# Pre-built adapter instances
# ---------------------------------------------------------------------------

FileReadAgentTool = _FilesystemToolAdapter(
    inner=FileReadTool(),
    metadata=ToolMetadata(
        tool_id="file_read",
        action_class="read",
        risk_level="low",
        required_permissions=["filesystem.read"],
        execution_policy="auto_execute",
        description="Read a file from the agent workspace. Returns numbered lines.",
    ),
)

FileWriteAgentTool = _FilesystemToolAdapter(
    inner=FileWriteTool(),
    metadata=ToolMetadata(
        tool_id="file_write",
        action_class="draft",
        risk_level="medium",
        required_permissions=["filesystem.write"],
        execution_policy="auto_execute",
        description="Write content to a file in the agent workspace. Creates parent directories.",
    ),
)

FileEditAgentTool = _FilesystemToolAdapter(
    inner=FileEditTool(),
    metadata=ToolMetadata(
        tool_id="file_edit",
        action_class="draft",
        risk_level="medium",
        required_permissions=["filesystem.write"],
        execution_policy="auto_execute",
        description="Replace exact text in a file. The old_text must appear exactly once.",
    ),
)

FileSearchAgentTool = _FilesystemToolAdapter(
    inner=FileSearchTool(),
    metadata=ToolMetadata(
        tool_id="file_search",
        action_class="read",
        risk_level="low",
        required_permissions=["filesystem.read"],
        execution_policy="auto_execute",
        description="Search file contents in the workspace using a regex pattern.",
    ),
)

FileListAgentTool = _FilesystemToolAdapter(
    inner=FileListTool(),
    metadata=ToolMetadata(
        tool_id="file_list",
        action_class="read",
        risk_level="low",
        required_permissions=["filesystem.read"],
        execution_policy="auto_execute",
        description="List files and directories in the agent workspace.",
    ),
)

FILESYSTEM_AGENT_TOOLS = [
    FileReadAgentTool,
    FileWriteAgentTool,
    FileEditAgentTool,
    FileSearchAgentTool,
    FileListAgentTool,
]
