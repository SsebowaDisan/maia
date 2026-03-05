from __future__ import annotations

from pathlib import Path
from typing import Any

from api.services.agent.models import AgentSource
from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionResult, ToolMetadata, ToolTraceEvent

from .base import WorkspaceConnectorTool
from .common import chunk_text, drain_stream, resolve_public_share_options


class WorkspaceDocsTemplateTool(WorkspaceConnectorTool):
    metadata = ToolMetadata(
        tool_id="workspace.docs.fill_template",
        action_class="draft",
        risk_level="medium",
        required_permissions=["docs.write"],
        execution_policy="auto_execute",
        description="Create a Google Doc and replace template placeholders.",
    )

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ):
        title = str(params.get("title") or "Maia Generated Document").strip()
        replacements = params.get("replacements")
        if not isinstance(replacements, dict):
            replacements = {}
        prompt_text = str(params.get("body") or prompt).strip()
        render_markdown = bool(params.get("render_markdown", True))
        make_public, public_role, public_discoverable = resolve_public_share_options(
            params=params,
            settings=context.settings,
        )
        connector = self._workspace_connector(settings=context.settings)

        trace_events: list[ToolTraceEvent] = []
        open_event = ToolTraceEvent(event_type="doc_open", title="Create Google Doc", detail=title)
        trace_events.append(open_event)
        yield open_event

        docs_create_started = ToolTraceEvent(
            event_type="docs.create_started",
            title="Start Google Doc creation",
            detail=title,
            data={"title": title},
        )
        trace_events.append(docs_create_started)
        yield docs_create_started
        created = connector.create_docs_document(title=title)
        document_id = str(created.get("documentId") or "")
        doc_url = f"https://docs.google.com/document/d/{document_id}/edit" if document_id else ""
        if document_id:
            context.settings["__latest_report_document_id"] = document_id
            context.settings["__latest_report_document_url"] = doc_url
            context.settings["__latest_report_title"] = title
        docs_create_completed = ToolTraceEvent(
            event_type="docs.create_completed",
            title="Google Doc created",
            detail=document_id or title,
            data={"doc_id": document_id, "document_url": doc_url, "source_url": doc_url},
        )
        trace_events.append(docs_create_completed)
        yield docs_create_completed
        public_shared = False
        public_share_error = ""
        if make_public and document_id:
            share_start = ToolTraceEvent(
                event_type="drive.share_started",
                title="Enable public link access for document",
                detail=document_id,
                data={
                    "file_id": document_id,
                    "role": public_role,
                    "scope": "anyone",
                    "discoverable": public_discoverable,
                    "source_url": doc_url,
                },
            )
            trace_events.append(share_start)
            yield share_start
            try:
                connector.share_drive_file_public(
                    file_id=document_id,
                    role=public_role,
                    discoverable=public_discoverable,
                )
                public_shared = True
                share_done = ToolTraceEvent(
                    event_type="drive.share_completed",
                    title="Public link access enabled for document",
                    detail=document_id,
                    data={
                        "file_id": document_id,
                        "role": public_role,
                        "scope": "anyone",
                        "discoverable": public_discoverable,
                        "source_url": doc_url,
                    },
                )
                trace_events.append(share_done)
                yield share_done
            except Exception as exc:
                public_share_error = str(exc)
                share_failed = ToolTraceEvent(
                    event_type="drive.share_failed",
                    title="Failed to enable public link access for document",
                    detail=public_share_error[:200],
                    data={
                        "file_id": document_id,
                        "role": public_role,
                        "scope": "anyone",
                        "discoverable": public_discoverable,
                        "source_url": doc_url,
                        "error": public_share_error[:300],
                    },
                )
                trace_events.append(share_failed)
                yield share_failed
        if doc_url:
            go_to_doc_event = ToolTraceEvent(
                event_type="drive.go_to_doc",
                title="Open document link",
                detail=doc_url,
                data={"source_url": doc_url, "document_url": doc_url, "doc_id": document_id},
            )
            trace_events.append(go_to_doc_event)
            yield go_to_doc_event
        if replacements and document_id:
            replacement_summary = ", ".join(
                f"{str(key)}={str(value)[:30]}" for key, value in list(replacements.items())[:4]
            )
            if replacement_summary:
                copy_event = ToolTraceEvent(
                    event_type="doc_copy_clipboard",
                    title="Copy template values",
                    detail=replacement_summary,
                    data={"document_id": document_id},
                )
                trace_events.append(copy_event)
                yield copy_event
            paste_event = ToolTraceEvent(
                event_type="doc_paste_clipboard",
                title="Paste values into placeholders",
                detail=f"{len(replacements)} mapped values",
                data={"document_id": document_id},
            )
            trace_events.append(paste_event)
            yield paste_event
            replace_event = ToolTraceEvent(
                event_type="doc_insert_text",
                title="Apply template replacements",
                detail=f"{len(replacements)} placeholder(s)",
                data={"document_id": document_id},
            )
            trace_events.append(replace_event)
            yield replace_event
            replace_started = ToolTraceEvent(
                event_type="docs.replace_started",
                title="Start placeholder replacement",
                detail=f"{len(replacements)} placeholder(s)",
                data={"doc_id": document_id, "count": len(replacements), "source_url": doc_url},
            )
            trace_events.append(replace_started)
            yield replace_started
            connector.docs_replace_text(document_id=document_id, replacements=replacements)
            replace_completed = ToolTraceEvent(
                event_type="docs.replace_completed",
                title="Placeholder replacement completed",
                detail=f"{len(replacements)} placeholder(s)",
                data={"doc_id": document_id, "count": len(replacements), "source_url": doc_url},
            )
            trace_events.append(replace_completed)
            yield replace_completed

        if prompt_text and document_id:
            chunks = chunk_text(prompt_text, chunk_size=170, max_chunks=5)
            for chunk_index, chunk in enumerate(chunks, start=1):
                typing_event = ToolTraceEvent(
                    event_type="doc_type_text",
                    title=f"Compose content chunk {chunk_index}/{len(chunks)}",
                    detail=chunk,
                    data={
                        "document_id": document_id,
                        "chunk_index": chunk_index,
                        "chunk_total": len(chunks),
                    },
                )
                trace_events.append(typing_event)
                yield typing_event

        export_requested = bool(params.get("export_pdf"))
        pdf_path = ""
        if export_requested and document_id:
            export_event = ToolTraceEvent(
                event_type="tool_progress",
                title="Export Google Doc to PDF",
                detail=document_id,
                data={"document_id": document_id},
            )
            trace_events.append(export_event)
            yield export_event
            pdf_bytes = connector.export_drive_file_pdf(file_id=document_id)
            out_dir = Path(".maia_agent") / "documents"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{document_id}.pdf"
            out_file.write_bytes(pdf_bytes)
            pdf_path = str(out_file.resolve())
            if pdf_path:
                context.settings["__latest_report_pdf_path"] = pdf_path

        if prompt_text and document_id:
            insert_started = ToolTraceEvent(
                event_type="docs.insert_started",
                title="Start appending text",
                detail=f"{len(prompt_text)} characters",
                data={
                    "doc_id": document_id,
                    "characters": len(prompt_text),
                    "source_url": doc_url,
                    "render_mode": "markdown" if render_markdown else "plain_text",
                },
            )
            trace_events.append(insert_started)
            yield insert_started
            if render_markdown and hasattr(connector, "docs_insert_markdown"):
                connector.docs_insert_markdown(document_id=document_id, markdown_text=f"\n\n{prompt_text}\n")
            else:
                connector.docs_insert_text(document_id=document_id, text=f"\n\n{prompt_text}\n")
            insert_completed = ToolTraceEvent(
                event_type="docs.insert_completed",
                title="Appended text to Google Doc",
                detail=f"{len(prompt_text)} characters",
                data={
                    "doc_id": document_id,
                    "characters": len(prompt_text),
                    "source_url": doc_url,
                    "render_mode": "markdown" if render_markdown else "plain_text",
                },
            )
            trace_events.append(insert_completed)
            yield insert_completed

        save_event = ToolTraceEvent(
            event_type="doc_save",
            title="Persist Google Doc",
            detail=document_id or "document saved",
            data={"document_id": document_id, "document_url": doc_url, "source_url": doc_url},
        )
        trace_events.append(save_event)
        yield save_event

        details = [
            f"Created Google Doc `{title}`.",
            f"- Document ID: {document_id or 'unknown'}",
            f"- URL: {doc_url or 'not available'}",
            f"- Replacements applied: {len(replacements)}",
            f"- Public link enabled: {'yes' if public_shared else 'no'}",
        ]
        if prompt_text:
            details.append(f"- Prompt context length: {len(prompt_text)} chars")
        if pdf_path:
            details.append(f"- Exported PDF: {pdf_path}")

        return ToolExecutionResult(
            summary=f"Google Doc created: {title}.",
            content="\n".join(details),
            data={
                "document_id": document_id,
                "url": doc_url,
                "replacements_count": len(replacements),
                "pdf_path": pdf_path or None,
                "render_markdown": render_markdown,
                "public_shared": public_shared,
                "public_role": public_role if make_public else "",
                "public_discoverable": public_discoverable if make_public else False,
                "public_share_error": public_share_error,
            },
            sources=[
                AgentSource(
                    source_type="web",
                    label=title,
                    url=doc_url or None,
                    score=0.7,
                    metadata={"provider": "google_docs", "document_id": document_id},
                )
            ],
            next_steps=["Review generated document and share with stakeholders."],
            events=trace_events,
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        return drain_stream(self.execute_stream(context=context, prompt=prompt, params=params))
