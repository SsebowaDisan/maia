from __future__ import annotations

from typing import Any

from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)

from .base import WorkspaceConnectorTool
from .common import chunk_text, drain_stream, now_iso, resolve_public_share_options, scene_payload


class WorkspaceResearchNotesTool(WorkspaceConnectorTool):
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
        include_copied_highlights = bool(params.get("include_copied_highlights", True))
        if include_copied_highlights:
            copied_rows = context.settings.get("__copied_highlights")
            copied_lines: list[str] = []
            if isinstance(copied_rows, list):
                for row in copied_rows[-8:]:
                    if not isinstance(row, dict):
                        continue
                    snippet = " ".join(str(row.get("text") or "").split()).strip()
                    if not snippet:
                        continue
                    word = str(row.get("word") or "").strip()
                    reference = str(row.get("reference") or row.get("title") or "").strip()
                    bullet = "- "
                    if word:
                        bullet += f"{word}: "
                    bullet += snippet[:220]
                    if reference:
                        bullet += f" ({reference})"
                    copied_lines.append(bullet)
                    if len(copied_lines) >= 5:
                        break
            if copied_lines:
                note = "\n".join([note, "", "Copied highlights:", *copied_lines]).strip()
        title = str(params.get("title") or "").strip() or f"Maia Deep Research {context.run_id[:8]}"
        make_public, public_role, public_discoverable = resolve_public_share_options(
            params=params,
            settings=context.settings,
        )
        connector = self._workspace_connector(settings=context.settings)

        document_id = str(context.settings.get("__deep_research_doc_id") or "").strip()
        document_url = str(context.settings.get("__deep_research_doc_url") or "").strip()
        trace_events: list[ToolTraceEvent] = []

        def _doc_scene(
            *,
            lane: str,
            payload: dict[str, Any] | None = None,
            primary_index: int = 1,
            secondary_index: int = 1,
        ) -> dict[str, Any]:
            return scene_payload(
                surface="google_docs",
                lane=lane,
                primary_index=primary_index,
                secondary_index=secondary_index,
                payload=payload,
            )

        open_event = ToolTraceEvent(
            event_type="doc_open",
            title="Open Google research notebook",
            detail=document_url or document_id or title,
            data=_doc_scene(
                lane="research-note-open",
                payload={
                    "document_id": document_id,
                    "document_url": document_url,
                    "source_url": document_url,
                },
            ),
        )
        trace_events.append(open_event)
        yield open_event

        created_now = False
        public_shared = bool(context.settings.get("__deep_research_doc_public_shared"))
        public_share_error = ""
        if not document_id:
            create_event = ToolTraceEvent(
                event_type="doc_open",
                title="Create Google research notebook",
                detail=title,
                data=_doc_scene(
                    lane="research-note-create-open",
                    payload={"document_id": "", "document_url": ""},
                ),
            )
            trace_events.append(create_event)
            yield create_event
            docs_create_started = ToolTraceEvent(
                event_type="docs.create_started",
                title="Start Google research notebook creation",
                detail=title,
                data=_doc_scene(
                    lane="research-note-create-start",
                    payload={"title": title},
                ),
            )
            trace_events.append(docs_create_started)
            yield docs_create_started
            created = connector.create_docs_document(title=title)
            document_id = str(created.get("documentId") or "").strip()
            document_url = (
                f"https://docs.google.com/document/d/{document_id}/edit" if document_id else ""
            )
            context.settings["__deep_research_doc_id"] = document_id
            context.settings["__deep_research_doc_url"] = document_url
            created_now = True
            docs_create_completed = ToolTraceEvent(
                event_type="docs.create_completed",
                title="Google research notebook created",
                detail=document_id or title,
                data=_doc_scene(
                    lane="research-note-create-done",
                    payload={
                        "doc_id": document_id,
                        "document_url": document_url,
                        "source_url": document_url,
                    },
                ),
            )
            trace_events.append(docs_create_completed)
            yield docs_create_completed
            if document_url:
                go_to_doc_event = ToolTraceEvent(
                    event_type="drive.go_to_doc",
                    title="Open research notebook link",
                    detail=document_url,
                    data=_doc_scene(
                        lane="research-note-open-link",
                        payload={
                            "source_url": document_url,
                            "document_url": document_url,
                            "doc_id": document_id,
                        },
                    ),
                )
                trace_events.append(go_to_doc_event)
                yield go_to_doc_event
        should_share_public = bool(
            make_public and document_id and (created_now or not public_shared)
        )
        if should_share_public:
            share_start = ToolTraceEvent(
                event_type="drive.share_started",
                title="Enable public link access for research notebook",
                detail=document_id,
                data=_doc_scene(
                    lane="research-note-share-start",
                    payload={
                        "file_id": document_id,
                        "role": public_role,
                        "scope": "anyone",
                        "discoverable": public_discoverable,
                        "source_url": document_url,
                    },
                ),
            )
            trace_events.append(share_start)
            yield share_start
            try:
                connector.share_drive_file_public(
                    file_id=document_id,
                    role=public_role,
                    discoverable=public_discoverable,
                )
                context.settings["__deep_research_doc_public_shared"] = True
                public_shared = True
                share_done = ToolTraceEvent(
                    event_type="drive.share_completed",
                    title="Public link access enabled",
                    detail=document_id,
                    data=_doc_scene(
                        lane="research-note-share-done",
                        payload={
                            "file_id": document_id,
                            "role": public_role,
                            "scope": "anyone",
                            "discoverable": public_discoverable,
                            "source_url": document_url,
                        },
                    ),
                )
                trace_events.append(share_done)
                yield share_done
            except Exception as exc:
                public_share_error = str(exc)
                share_failed = ToolTraceEvent(
                    event_type="drive.share_failed",
                    title="Failed to enable public link access",
                    detail=public_share_error[:200],
                    data=_doc_scene(
                        lane="research-note-share-failed",
                        payload={
                            "file_id": document_id,
                            "role": public_role,
                            "scope": "anyone",
                            "discoverable": public_discoverable,
                            "source_url": document_url,
                            "error": public_share_error[:300],
                        },
                    ),
                )
                trace_events.append(share_failed)
                yield share_failed
        clipboard_source = chunk_text(note, chunk_size=220, max_chunks=1)
        if clipboard_source:
            copy_event = ToolTraceEvent(
                event_type="doc_copy_clipboard",
                title="Copy web highlights to clipboard",
                detail=clipboard_source[0],
                data=_doc_scene(
                    lane="research-note-copy",
                    payload={
                        "document_id": document_id,
                        "clipboard_text": clipboard_source[0],
                        "source_url": document_url,
                    },
                ),
            )
            trace_events.append(copy_event)
            yield copy_event

        anchor_event = ToolTraceEvent(
            event_type="doc_locate_anchor",
            title="Locate notebook insertion point",
            detail="Moving cursor to the end of document",
            data=_doc_scene(
                lane="research-note-anchor",
                payload={"document_id": document_id, "source_url": document_url},
            ),
        )
        trace_events.append(anchor_event)
        yield anchor_event

        note_block = f"\n\n[{now_iso()}]\n{note}\n"
        if document_id:
            paste_preview = chunk_text(note_block, chunk_size=220, max_chunks=1)
            paste_event = ToolTraceEvent(
                event_type="doc_paste_clipboard",
                title="Paste clipboard into Google Doc",
                detail=paste_preview[0] if paste_preview else "Pasted note block",
                data=_doc_scene(
                    lane="research-note-paste",
                    payload={
                        "document_id": document_id,
                        "clipboard_text": paste_preview[0] if paste_preview else "",
                        "source_url": document_url,
                    },
                ),
            )
            trace_events.append(paste_event)
            yield paste_event

            typed_chunks = chunk_text(note_block, chunk_size=160, max_chunks=8)
            for chunk_index, chunk in enumerate(typed_chunks, start=1):
                typing_event = ToolTraceEvent(
                    event_type="doc_type_text",
                    title=f"Type note chunk {chunk_index}/{len(typed_chunks)}",
                    detail=chunk,
                    data=_doc_scene(
                        lane="research-note-type",
                        primary_index=chunk_index,
                        secondary_index=max(1, len(typed_chunks)),
                        payload={
                            "document_id": document_id,
                            "chunk_index": chunk_index,
                            "chunk_total": len(typed_chunks),
                            "source_url": document_url,
                        },
                    ),
                )
                trace_events.append(typing_event)
                yield typing_event

            insert_event = ToolTraceEvent(
                event_type="doc_insert_text",
                title="Append research note",
                detail=f"{len(note_block)} characters",
                data=_doc_scene(
                    lane="research-note-insert",
                    payload={
                        "document_id": document_id,
                        "source_url": document_url,
                    },
                ),
            )
            trace_events.append(insert_event)
            yield insert_event
            insert_started = ToolTraceEvent(
                event_type="docs.insert_started",
                title="Start writing note to Google Doc",
                detail=f"{len(note_block)} characters",
                data=_doc_scene(
                    lane="research-note-insert-start",
                    payload={
                        "doc_id": document_id,
                        "characters": len(note_block),
                        "source_url": document_url,
                    },
                ),
            )
            trace_events.append(insert_started)
            yield insert_started
            connector.docs_insert_text(document_id=document_id, text=note_block)
            insert_completed = ToolTraceEvent(
                event_type="docs.insert_completed",
                title="Research note appended",
                detail=f"{len(note_block)} characters",
                data=_doc_scene(
                    lane="research-note-insert-done",
                    payload={
                        "doc_id": document_id,
                        "characters": len(note_block),
                        "source_url": document_url,
                    },
                ),
            )
            trace_events.append(insert_completed)
            yield insert_completed

        save_event = ToolTraceEvent(
            event_type="doc_save",
            title="Save research notebook",
            detail=document_id or "notebook saved",
            data=_doc_scene(
                lane="research-note-save",
                payload={
                    "document_id": document_id,
                    "document_url": document_url,
                    "source_url": document_url,
                },
            ),
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
                f"Public link enabled: {'yes' if public_shared else 'no'}",
            ]
        )
        if public_share_error:
            content = "\n".join([content, f"Public sharing error: {public_share_error}"])

        return ToolExecutionResult(
            summary=summary,
            content=content,
            data={
                "document_id": document_id,
                "document_url": document_url,
                "inserted_chars": len(note_block),
                "created_now": created_now,
                "public_shared": public_shared,
                "public_role": public_role if make_public else "",
                "public_discoverable": public_discoverable if make_public else False,
                "public_share_error": public_share_error,
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
        return drain_stream(self.execute_stream(context=context, prompt=prompt, params=params))
