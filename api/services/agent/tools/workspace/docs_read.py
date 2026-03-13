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


class WorkspaceDocsReadTool(WorkspaceConnectorTool):
    metadata = ToolMetadata(
        tool_id="workspace.docs.read",
        action_class="read",
        risk_level="low",
        required_permissions=["docs.read"],
        execution_policy="auto_execute",
        description="Read the full text content of a Google Doc.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        document_id = str(params.get("document_id") or params.get("doc_id") or "").strip()

        # Try to parse from URL if raw ID not given
        if not document_id:
            for key in ("document_url", "doc_url", "url", "link"):
                raw = str(params.get(key) or "").strip()
                if "docs.google.com/document/d/" in raw:
                    after = raw.split("docs.google.com/document/d/")[1]
                    document_id = after.split("/")[0].split("?")[0].strip()
                    if document_id:
                        break

        if not document_id:
            document_id = str(
                context.settings.get("__latest_report_document_id")
                or context.settings.get("__deep_research_doc_id")
                or ""
            ).strip()

        if not document_id:
            raise ToolExecutionError(
                "`document_id` is required. Provide document_id, a Google Docs URL, or use after workspace.docs.fill_template."
            )

        doc_url = f"https://docs.google.com/document/d/{document_id}/edit"
        connector = self._workspace_connector(settings=context.settings)
        response = connector.docs_read_text(document_id=document_id)

        title = str(response.get("title") or "Untitled")
        text = str(response.get("text") or "")
        char_count = len(text)

        # Truncate preview for content field (full text in data)
        preview = text[:2000]
        if char_count > 2000:
            preview += f"\n... ({char_count - 2000} more characters)"

        events = [
            ToolTraceEvent(
                event_type="doc_open",
                title="Open Google Doc",
                detail=document_id,
                data=scene_payload(
                    surface="google_docs",
                    lane="doc-open",
                    payload={
                        "document_id": document_id,
                        "document_url": doc_url,
                        "source_url": doc_url,
                    },
                ),
            ),
            ToolTraceEvent(
                event_type="docs.read_completed",
                title="Document content read",
                detail=f'"{title}" — {char_count} characters',
                data=scene_payload(
                    surface="google_docs",
                    lane="doc-read-done",
                    payload={
                        "document_id": document_id,
                        "title": title,
                        "characters": char_count,
                        "source_url": doc_url,
                    },
                ),
            ),
        ]

        return ToolExecutionResult(
            summary=f'Read Google Doc "{title}" ({char_count} characters).',
            content=preview or "(document is empty)",
            data={
                "document_id": document_id,
                "document_url": doc_url,
                "title": title,
                "text": text,
                "character_count": char_count,
            },
            sources=[],
            next_steps=[
                "Use workspace.docs.fill_template to update the document based on the content read."
            ],
            events=events,
        )
