from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chunk_text(text: str, *, chunk_size: int = 180, max_chunks: int = 8) -> list[str]:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return []
    chunks: list[str] = []
    cursor = 0
    size = max(40, int(chunk_size))
    while cursor < len(cleaned) and len(chunks) < max(1, int(max_chunks)):
        chunks.append(cleaned[cursor : cursor + size])
        cursor += size
    if cursor < len(cleaned):
        chunks[-1] = f"{chunks[-1]}..."
    return chunks


def _sheet_col_name(index_zero_based: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if index_zero_based < 0:
        return "A"
    name = ""
    index = index_zero_based
    while True:
        name = alphabet[index % 26] + name
        index = index // 26 - 1
        if index < 0:
            break
    return name


class WorkspaceDriveSearchTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="workspace.drive.search",
        action_class="read",
        risk_level="low",
        required_permissions=["drive.read"],
        execution_policy="auto_execute",
        description="Search Google Drive files for workflow context.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        query = str(params.get("query") or prompt).strip()
        connector = get_connector_registry().build("google_workspace", settings=context.settings)
        response = connector.list_drive_files(query=query)
        files = response.get("files") if isinstance(response, dict) else []
        if not isinstance(files, list):
            files = []

        lines = [f"### Google Drive results ({len(files)})"]
        sources: list[AgentSource] = []
        for row in files[:12]:
            if not isinstance(row, dict):
                continue
            file_id = str(row.get("id") or "")
            name = str(row.get("name") or "Drive file")
            mime_type = str(row.get("mimeType") or "")
            drive_url = f"https://drive.google.com/file/d/{file_id}/view" if file_id else ""
            lines.append(f"- {name} ({mime_type or 'unknown'})")
            sources.append(
                AgentSource(
                    source_type="web",
                    label=name,
                    url=drive_url or None,
                    score=0.65,
                    metadata={"provider": "google_drive", "file_id": file_id},
                )
            )
        if len(lines) == 1:
            lines.append("- No files found.")

        return ToolExecutionResult(
            summary=f"Found {len(files)} Drive file(s).",
            content="\n".join(lines),
            data={"query": query, "count": len(files)},
            sources=sources,
            next_steps=["Open selected files and connect them to report generation."],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Search Google Drive",
                    detail=query or "recent files",
                    data={"count": len(files)},
                )
            ],
        )


class WorkspaceSheetsAppendTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="workspace.sheets.append",
        action_class="execute",
        risk_level="high",
        required_permissions=["sheets.write"],
        execution_policy="confirm_before_execute",
        description="Append rows to Google Sheets for CRM/analytics tracking.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        spreadsheet_id = str(params.get("spreadsheet_id") or "").strip()
        sheet_range = str(params.get("sheet_range") or "Sheet1!A1").strip()
        values = params.get("values")
        if not spreadsheet_id:
            raise ToolExecutionError("`spreadsheet_id` is required.")
        if not isinstance(values, list) or not values:
            raise ToolExecutionError("`values` must be a non-empty 2D array.")

        connector = get_connector_registry().build("google_workspace", settings=context.settings)
        response = connector.append_sheet_values(
            spreadsheet_id=spreadsheet_id,
            sheet_range=sheet_range,
            values=values,
        )
        updated_rows = (
            (response.get("updates") or {}).get("updatedRows")
            if isinstance(response, dict)
            else 0
        )

        return ToolExecutionResult(
            summary=f"Appended rows to Google Sheet ({updated_rows or 0} updated).",
            content=(
                f"Rows appended to spreadsheet `{spreadsheet_id}` at range `{sheet_range}`.\n"
                f"- Updated rows: {updated_rows or 0}"
            ),
            data={"spreadsheet_id": spreadsheet_id, "sheet_range": sheet_range, "updated_rows": updated_rows},
            sources=[],
            next_steps=["Verify appended rows and apply formatting rules if needed."],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Append rows to Google Sheets",
                    detail=f"{spreadsheet_id} :: {sheet_range}",
                    data={"updated_rows": updated_rows or 0},
                )
            ],
        )


class WorkspaceDocsTemplateTool(AgentTool):
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
        connector = get_connector_registry().build("google_workspace", settings=context.settings)

        trace_events: list[ToolTraceEvent] = []
        open_event = ToolTraceEvent(event_type="doc_open", title="Create Google Doc", detail=title)
        trace_events.append(open_event)
        yield open_event

        created = connector.create_docs_document(title=title)
        document_id = str(created.get("documentId") or "")
        doc_url = f"https://docs.google.com/document/d/{document_id}/edit" if document_id else ""
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
            connector.docs_replace_text(document_id=document_id, replacements=replacements)

        if prompt_text and document_id:
            chunks = _chunk_text(prompt_text, chunk_size=170, max_chunks=5)
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

        save_event = ToolTraceEvent(
            event_type="doc_save",
            title="Persist Google Doc",
            detail=document_id or "document saved",
            data={"document_id": document_id, "url": doc_url},
        )
        trace_events.append(save_event)
        yield save_event

        details = [
            f"Created Google Doc `{title}`.",
            f"- Document ID: {document_id or 'unknown'}",
            f"- URL: {doc_url or 'not available'}",
            f"- Replacements applied: {len(replacements)}",
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
        stream = self.execute_stream(context=context, prompt=prompt, params=params)
        traces: list[ToolTraceEvent] = []
        while True:
            try:
                traces.append(next(stream))
            except StopIteration as stop:
                result = stop.value
                break
        result.events = traces
        return result


class WorkspaceResearchNotesTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="workspace.docs.research_notes",
        action_class="draft",
        risk_level="medium",
        required_permissions=["docs.write"],
        execution_policy="auto_execute",
        description="Append deep research notes into a dedicated Google Doc.",
    )

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ):
        note = str(params.get("note") or prompt).strip()
        if not note:
            raise ToolExecutionError("`note` is required.")
        title = str(params.get("title") or "").strip() or f"Maia Deep Research {context.run_id[:8]}"
        connector = get_connector_registry().build("google_workspace", settings=context.settings)

        document_id = str(context.settings.get("__deep_research_doc_id") or "").strip()
        document_url = str(context.settings.get("__deep_research_doc_url") or "").strip()
        trace_events: list[ToolTraceEvent] = []
        open_event = ToolTraceEvent(
            event_type="doc_open",
            title="Open Google research notebook",
            detail=document_url or document_id or title,
            data={"document_id": document_id, "document_url": document_url},
        )
        trace_events.append(open_event)
        yield open_event

        created_now = False
        if not document_id:
            create_event = ToolTraceEvent(
                event_type="doc_open",
                title="Create Google research notebook",
                detail=title,
                data={"document_id": "", "document_url": ""},
            )
            trace_events.append(create_event)
            yield create_event
            created = connector.create_docs_document(title=title)
            document_id = str(created.get("documentId") or "").strip()
            document_url = (
                f"https://docs.google.com/document/d/{document_id}/edit" if document_id else ""
            )
            context.settings["__deep_research_doc_id"] = document_id
            context.settings["__deep_research_doc_url"] = document_url
            created_now = True
        clipboard_source = _chunk_text(note, chunk_size=220, max_chunks=1)
        if clipboard_source:
            copy_event = ToolTraceEvent(
                event_type="doc_copy_clipboard",
                title="Copy web highlights to clipboard",
                detail=clipboard_source[0],
                data={
                    "document_id": document_id,
                    "clipboard_text": clipboard_source[0],
                },
            )
            trace_events.append(copy_event)
            yield copy_event

        anchor_event = ToolTraceEvent(
            event_type="doc_locate_anchor",
            title="Locate notebook insertion point",
            detail="Moving cursor to the end of document",
            data={"document_id": document_id},
        )
        trace_events.append(anchor_event)
        yield anchor_event

        note_block = f"\n\n[{_now_iso()}]\n{note}\n"
        if document_id:
            paste_preview = _chunk_text(note_block, chunk_size=220, max_chunks=1)
            paste_event = ToolTraceEvent(
                event_type="doc_paste_clipboard",
                title="Paste clipboard into Google Doc",
                detail=paste_preview[0] if paste_preview else "Pasted note block",
                data={
                    "document_id": document_id,
                    "clipboard_text": paste_preview[0] if paste_preview else "",
                },
            )
            trace_events.append(paste_event)
            yield paste_event

            typed_chunks = _chunk_text(note_block, chunk_size=160, max_chunks=8)
            for chunk_index, chunk in enumerate(typed_chunks, start=1):
                typing_event = ToolTraceEvent(
                    event_type="doc_type_text",
                    title=f"Type note chunk {chunk_index}/{len(typed_chunks)}",
                    detail=chunk,
                    data={
                        "document_id": document_id,
                        "chunk_index": chunk_index,
                        "chunk_total": len(typed_chunks),
                    },
                )
                trace_events.append(typing_event)
                yield typing_event

            insert_event = ToolTraceEvent(
                event_type="doc_insert_text",
                title="Append research note",
                detail=f"{len(note_block)} characters",
                data={"document_id": document_id},
            )
            trace_events.append(insert_event)
            yield insert_event
            connector.docs_insert_text(document_id=document_id, text=note_block)

        save_event = ToolTraceEvent(
            event_type="doc_save",
            title="Save research notebook",
            detail=document_id or "notebook saved",
            data={"document_id": document_id, "document_url": document_url},
        )
        trace_events.append(save_event)
        yield save_event

        summary = "Updated deep research notebook." if document_id else "Could not update research notebook."
        content = "\n".join(
            [
                f"Notebook title: {title}",
                f"Document ID: {document_id or 'unknown'}",
                f"Document URL: {document_url or 'not available'}",
                f"Inserted characters: {len(note_block)}",
            ]
        )

        return ToolExecutionResult(
            summary=summary,
            content=content,
            data={
                "document_id": document_id,
                "document_url": document_url,
                "inserted_chars": len(note_block),
                "created_now": created_now,
            },
            sources=[
                AgentSource(
                    source_type="web",
                    label=title,
                    url=document_url or None,
                    score=0.72 if document_url else 0.5,
                    metadata={"provider": "google_docs", "document_id": document_id},
                )
            ]
            if document_id
            else [],
            next_steps=["Continue appending evidence notes as each step completes."],
            events=trace_events,
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        stream = self.execute_stream(context=context, prompt=prompt, params=params)
        traces: list[ToolTraceEvent] = []
        while True:
            try:
                traces.append(next(stream))
            except StopIteration as stop:
                result = stop.value
                break
        result.events = traces
        return result


class WorkspaceSheetsTrackStepTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="workspace.sheets.track_step",
        action_class="execute",
        risk_level="medium",
        required_permissions=["sheets.write"],
        execution_policy="auto_execute",
        description="Track deep research step progress in a Google Sheet.",
    )

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ):
        step_name = str(params.get("step_name") or prompt).strip() or "Unnamed step"
        status = str(params.get("status") or "completed").strip() or "completed"
        detail = str(params.get("detail") or "").strip()
        source_url = str(params.get("source_url") or "").strip()
        title = str(params.get("title") or "").strip() or f"Maia Deep Research Tracker {context.run_id[:8]}"
        sheet_name = str(params.get("sheet_name") or "Tracker").strip() or "Tracker"
        sheet_range = f"{sheet_name}!A1"
        connector = get_connector_registry().build("google_workspace", settings=context.settings)

        spreadsheet_id = str(context.settings.get("__deep_research_sheet_id") or "").strip()
        spreadsheet_url = str(context.settings.get("__deep_research_sheet_url") or "").strip()
        trace_events: list[ToolTraceEvent] = []
        open_event = ToolTraceEvent(
            event_type="sheet_open",
            title="Open Google Sheets tracker",
            detail=spreadsheet_url or spreadsheet_id or title,
            data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
        )
        trace_events.append(open_event)
        yield open_event

        header_written = bool(context.settings.get("__deep_research_sheet_header_written"))
        created_now = False
        if not spreadsheet_id:
            create_event = ToolTraceEvent(
                event_type="sheet_open",
                title="Create Google Sheets tracker",
                detail=title,
                data={"spreadsheet_id": "", "spreadsheet_url": ""},
            )
            trace_events.append(create_event)
            yield create_event
            created = connector.create_spreadsheet(title=title, sheet_title=sheet_name)
            spreadsheet_id = str(created.get("spreadsheet_id") or "").strip()
            spreadsheet_url = str(created.get("spreadsheet_url") or "").strip()
            context.settings["__deep_research_sheet_id"] = spreadsheet_id
            context.settings["__deep_research_sheet_url"] = spreadsheet_url
            context.settings["__deep_research_sheet_range"] = sheet_range
            header_written = False
            created_now = True

        if spreadsheet_id and not header_written:
            connector.append_sheet_values(
                spreadsheet_id=spreadsheet_id,
                sheet_range=sheet_range,
                values=[["timestamp", "run_id", "step", "status", "detail", "source_url"]],
            )
            context.settings["__deep_research_sheet_header_written"] = True

        row_values = [_now_iso(), context.run_id, step_name, status, detail, source_url]
        for cell_index, cell_value in enumerate(row_values):
            cell_event = ToolTraceEvent(
                event_type="sheet_cell_update",
                title=f"Update cell {_sheet_col_name(cell_index)}",
                detail=str(cell_value)[:140],
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "column": _sheet_col_name(cell_index),
                    "value": str(cell_value),
                },
            )
            trace_events.append(cell_event)
            yield cell_event

        append_event = ToolTraceEvent(
            event_type="sheet_append_row",
            title="Append tracker row",
            detail=f"{step_name} ({status})",
            data={"spreadsheet_id": spreadsheet_id, "sheet_range": sheet_range},
        )
        trace_events.append(append_event)
        yield append_event

        response = (
            connector.append_sheet_values(
                spreadsheet_id=spreadsheet_id,
                sheet_range=sheet_range,
                values=[row_values],
            )
            if spreadsheet_id
            else {}
        )
        updated_rows = (
            (response.get("updates") or {}).get("updatedRows")
            if isinstance(response, dict)
            else 0
        )
        save_event = ToolTraceEvent(
            event_type="sheet_save",
            title="Save tracker updates",
            detail=spreadsheet_id or "tracker saved",
            data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
        )
        trace_events.append(save_event)
        yield save_event

        return ToolExecutionResult(
            summary=f"Tracked step `{step_name}` in Google Sheets.",
            content="\n".join(
                [
                    f"Spreadsheet ID: {spreadsheet_id or 'unknown'}",
                    f"Spreadsheet URL: {spreadsheet_url or 'not available'}",
                    f"Step: {step_name}",
                    f"Status: {status}",
                    f"Updated rows: {updated_rows or 0}",
                ]
            ),
            data={
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet_url": spreadsheet_url,
                "updated_rows": updated_rows or 0,
                "step_name": step_name,
                "status": status,
                "created_now": created_now,
            },
            sources=[
                AgentSource(
                    source_type="web",
                    label=f"{title} ({sheet_name})",
                    url=spreadsheet_url or None,
                    score=0.7 if spreadsheet_url else 0.45,
                    metadata={"provider": "google_sheets", "spreadsheet_id": spreadsheet_id},
                )
            ]
            if spreadsheet_id
            else [],
            next_steps=["Continue marking each completed action in the tracker."],
            events=trace_events,
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        stream = self.execute_stream(context=context, prompt=prompt, params=params)
        traces: list[ToolTraceEvent] = []
        while True:
            try:
                traces.append(next(stream))
            except StopIteration as stop:
                result = stop.value
                break
        result.events = traces
        return result
