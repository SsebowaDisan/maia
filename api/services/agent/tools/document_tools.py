from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)


def _safe_slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.strip()).strip("-").lower()
    return cleaned or "document"


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _build_copied_highlights_section(raw: Any, *, limit: int = 14) -> str:
    if not isinstance(raw, list):
        return ""
    lines: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text") or "").split()).strip()
        if not text:
            continue
        color = str(item.get("color") or "yellow").strip().lower()
        color = "green" if color == "green" else "yellow"
        word = str(item.get("word") or "").strip()
        reference = str(item.get("reference") or item.get("title") or "").strip()
        line = f"- [{color}] "
        if word:
            line += f"{word}: "
        line += text
        if reference:
            line += f" ({reference})"
        lines.append(line)
        if len(lines) >= max(1, int(limit)):
            break
    if not lines:
        return ""
    return "\n".join(["## Copied Highlights", *lines])


class DocumentCreateTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="docs.create",
        action_class="draft",
        risk_level="medium",
        required_permissions=["docs.write"],
        execution_policy="auto_execute",
        description="Create a working document through configured workspace connector.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        title = str(params.get("title") or "Company Brief").strip()
        body = str(params.get("body") or prompt).strip() or "No content provided."
        provider = str(params.get("provider") or context.settings.get("agent.docs_provider") or "local").strip()
        render_markdown = _truthy(params.get("render_markdown"), default=True)
        include_copied_highlights = _truthy(params.get("include_copied_highlights"), default=False)
        make_public = _truthy(
            params.get("make_public"),
            default=_truthy(
                context.settings.get("agent.workspace_make_public"),
                default=_truthy(os.getenv("MAIA_WORKSPACE_MAKE_PUBLIC"), default=False),
            ),
        )
        public_role = str(
            params.get("public_role")
            or context.settings.get("agent.workspace_public_role")
            or os.getenv("MAIA_WORKSPACE_PUBLIC_ROLE")
            or "reader"
        ).strip().lower()
        if public_role not in {"reader", "commenter", "writer"}:
            public_role = "reader"
        public_discoverable = _truthy(
            params.get("public_discoverable"),
            default=_truthy(
                context.settings.get("agent.workspace_public_discoverable"),
                default=_truthy(os.getenv("MAIA_WORKSPACE_PUBLIC_DISCOVERABLE"), default=False),
            ),
        )
        copied_section = (
            _build_copied_highlights_section(context.settings.get("__copied_highlights"))
            if include_copied_highlights
            else ""
        )
        if copied_section:
            body = f"{body}\n\n{copied_section}"

        trace_events: list[ToolTraceEvent] = []
        trace_events.append(
            ToolTraceEvent(
                event_type="doc_open",
                title="Open document composer",
                detail=f"Provider: {provider}",
                data={"provider": provider, "title": title},
            )
        )
        trace_events.append(
            ToolTraceEvent(
                event_type="doc_locate_anchor",
                title="Locate first editable section",
                detail="Finding insertion anchor for generated content",
            )
        )
        if copied_section:
            preview_line = copied_section.splitlines()[1] if len(copied_section.splitlines()) > 1 else ""
            trace_events.append(
                ToolTraceEvent(
                    event_type="doc_copy_clipboard",
                    title="Copy highlighted words",
                    detail=preview_line[:160],
                    data={"include_copied_highlights": True},
                )
            )
            trace_events.append(
                ToolTraceEvent(
                    event_type="doc_paste_clipboard",
                    title="Paste highlighted words into document",
                    detail="Appending copied highlights section",
                    data={"include_copied_highlights": True},
                )
            )
        trace_events.append(
            ToolTraceEvent(
                event_type="doc_insert_text",
                title="Insert generated content",
                detail="Writing generated body into document",
                data={"body_length": len(body)},
            )
        )

        if provider == "google_workspace":
            connector = get_connector_registry().build("google_workspace", settings=context.settings)
            created = connector.create_docs_document(title=title)
            doc_id = str(created.get("documentId") or "")
            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit" if doc_id else ""
            if doc_id:
                context.settings["__latest_report_document_id"] = doc_id
                context.settings["__latest_report_document_url"] = doc_url
                context.settings["__latest_report_title"] = title
            public_shared = False
            public_share_error = ""
            if make_public and doc_id:
                trace_events.append(
                    ToolTraceEvent(
                        event_type="drive.share_started",
                        title="Enable public link access",
                        detail=doc_id,
                        data={
                            "file_id": doc_id,
                            "role": public_role,
                            "scope": "anyone",
                            "discoverable": public_discoverable,
                            "source_url": doc_url,
                        },
                    )
                )
                try:
                    connector.share_drive_file_public(
                        file_id=doc_id,
                        role=public_role,
                        discoverable=public_discoverable,
                    )
                    public_shared = True
                    trace_events.append(
                        ToolTraceEvent(
                            event_type="drive.share_completed",
                            title="Public link access enabled",
                            detail=doc_id,
                            data={
                                "file_id": doc_id,
                                "role": public_role,
                                "scope": "anyone",
                                "discoverable": public_discoverable,
                                "source_url": doc_url,
                            },
                        )
                    )
                except Exception as exc:
                    public_share_error = str(exc)
                    trace_events.append(
                        ToolTraceEvent(
                            event_type="drive.share_failed",
                            title="Failed to enable public link access",
                            detail=public_share_error[:200],
                            data={
                                "file_id": doc_id,
                                "role": public_role,
                                "scope": "anyone",
                                "discoverable": public_discoverable,
                                "source_url": doc_url,
                                "error": public_share_error[:300],
                            },
                        )
                    )
            if doc_id and body:
                trace_events.append(
                    ToolTraceEvent(
                        event_type="docs.insert_started",
                        title="Append content to Google Doc",
                        detail=f"{len(body)} characters",
                        data={
                            "doc_id": doc_id,
                            "characters": len(body),
                            "source_url": doc_url,
                            "render_mode": "markdown" if render_markdown else "plain_text",
                        },
                    )
                )
                if render_markdown and hasattr(connector, "docs_insert_markdown"):
                    connector.docs_insert_markdown(document_id=doc_id, markdown_text=f"\n\n{body}\n")
                else:
                    connector.docs_insert_text(document_id=doc_id, text=f"\n\n{body}\n")
                trace_events.append(
                    ToolTraceEvent(
                        event_type="docs.insert_completed",
                        title="Google Doc content appended",
                        detail=f"{len(body)} characters",
                        data={
                            "doc_id": doc_id,
                            "characters": len(body),
                            "source_url": doc_url,
                            "render_mode": "markdown" if render_markdown else "plain_text",
                        },
                    )
                )
            trace_events.append(
                ToolTraceEvent(
                    event_type="doc_save",
                    title="Save Google Doc",
                    detail="Document created via Google Docs API",
                    data={"document_id": doc_id, "url": doc_url},
                )
            )
            return ToolExecutionResult(
                summary=f"Created Google Doc: {title}",
                content=(
                    f"Created document `{title}` in Google Docs.\n"
                    f"- Document ID: {doc_id or 'unknown'}\n"
                    f"- URL: {doc_url or 'not available'}\n"
                    f"- Draft body length: {len(body)} characters\n"
                    f"- Public link enabled: {'yes' if public_shared else 'no'}"
                ),
                data={
                    "provider": provider,
                    "title": title,
                    "document_id": doc_id,
                    "url": doc_url,
                    "body_length": len(body),
                    "copied_highlights_included": bool(copied_section),
                    "render_markdown": render_markdown,
                    "public_shared": public_shared,
                    "public_role": public_role if make_public else "",
                    "public_discoverable": public_discoverable if make_public else False,
                    "public_share_error": public_share_error,
                },
                sources=[],
                next_steps=[
                    "Review and polish document sections.",
                    "Share document link with stakeholders.",
                ],
                events=trace_events,
            )

        out_dir = Path(".maia_agent") / "documents"
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"{_safe_slug(title)}.md"
        file_path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        context.settings["__latest_report_title"] = title
        context.settings["__latest_report_document_path"] = str(file_path.resolve())
        trace_events.append(
            ToolTraceEvent(
                event_type="doc_save",
                title="Save local document",
                detail=f"Saved markdown document at {file_path.as_posix()}",
                data={"path": str(file_path.resolve())},
            )
        )
        return ToolExecutionResult(
            summary=f"Created local document: {title}",
            content=(
                f"Created local document `{title}`.\n"
                f"- Path: {file_path.as_posix()}\n"
                f"- Draft body length: {len(body)} characters"
            ),
            data={
                "provider": "local",
                "title": title,
                "path": str(file_path.resolve()),
                "body_length": len(body),
                "copied_highlights_included": bool(copied_section),
            },
            sources=[],
            next_steps=[
                "Review content and adjust structure.",
                "Publish to Docs/Slack/Email channels.",
            ],
            events=trace_events,
        )
