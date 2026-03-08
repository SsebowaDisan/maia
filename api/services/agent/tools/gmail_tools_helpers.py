from __future__ import annotations

import re
from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import ToolExecutionError, ToolTraceEvent


EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
SUBJECT_PATTERN = re.compile(r"(?:subject[:=]|\bsubject\b)\s*['\"]?([^'\n\"]+)", re.IGNORECASE)


def _extract_email(text: str) -> str:
    match = EMAIL_PATTERN.search(text)
    return match.group(1).strip() if match else ""


def _extract_subject(text: str, default: str = "Company update") -> str:
    match = SUBJECT_PATTERN.search(text)
    if not match:
        return default
    subject = match.group(1).strip()
    return subject or default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _infer_dry_run(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        marker in lowered
        for marker in (
            "dry run",
            "dry-run",
            "preview only",
            "do not send",
            "don't send",
            "dont send",
            "test only",
        )
    )


def _chunk_text(text: str, *, chunk_size: int = 140, max_chunks: int = 8) -> list[str]:
    compact = " ".join(str(text or "").split())
    if not compact:
        return []
    chunks: list[str] = []
    cursor = 0
    size = max(30, int(chunk_size))
    while cursor < len(compact) and len(chunks) < max(1, int(max_chunks)):
        chunks.append(compact[cursor : cursor + size])
        cursor += size
    if cursor < len(compact):
        chunks[-1] = f"{chunks[-1]}..."
    return chunks


def _compact_text(value: Any, *, limit: int = 280) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 1)].rstrip()}..."


def _looks_like_path(value: str) -> bool:
    candidate = str(value or "").strip()
    if not candidate:
        return False
    if "/" in candidate or "\\" in candidate:
        return True
    if candidate.startswith("."):
        return True
    lowered = candidate.lower()
    return lowered.endswith(
        (
            ".pdf",
            ".doc",
            ".docx",
            ".txt",
            ".csv",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".png",
            ".jpg",
            ".jpeg",
        )
    )


def _normalize_attachment_row(item: Any) -> dict[str, str] | None:
    if isinstance(item, dict):
        local_path = str(
            item.get("local_path")
            or item.get("path")
            or item.get("pdf_path")
            or item.get("attachment_path")
            or ""
        ).strip()
        file_id = str(
            item.get("file_id")
            or item.get("document_id")
            or item.get("drive_file_id")
            or item.get("attachment_file_id")
            or ""
        ).strip()
        label = str(item.get("label") or item.get("name") or local_path or file_id).strip()
        if local_path:
            return {"local_path": local_path, "label": label or local_path}
        if file_id:
            return {"file_id": file_id, "label": label or file_id}
        return None

    text = str(item or "").strip()
    if not text:
        return None
    if _looks_like_path(text):
        return {"local_path": text, "label": text}
    return {"file_id": text, "label": text}


def _dedupe_attachments(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        local_path = str(row.get("local_path") or "").strip()
        file_id = str(row.get("file_id") or "").strip()
        if not local_path and not file_id:
            continue
        key = ("local_path", local_path) if local_path else ("file_id", file_id)
        if key in seen:
            continue
        seen.add(key)
        label = str(row.get("label") or local_path or file_id).strip() or (local_path or file_id)
        payload: dict[str, str] = {"label": label}
        if local_path:
            payload["local_path"] = local_path
        if file_id:
            payload["file_id"] = file_id
        deduped.append(payload)
    return deduped


def _resolve_attachments(
    *,
    context: ToolExecutionContext,
    params: dict[str, Any],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    raw_list = params.get("attachments")
    if isinstance(raw_list, list):
        for item in raw_list[:16]:
            normalized = _normalize_attachment_row(item)
            if normalized:
                rows.append(normalized)

    for value in (
        params.get("attachment_path"),
        params.get("local_path"),
        params.get("pdf_path"),
    ):
        normalized = _normalize_attachment_row({"local_path": value})
        if normalized:
            rows.append(normalized)

    for value in (
        params.get("attachment_file_id"),
        params.get("file_id"),
        params.get("document_id"),
    ):
        normalized = _normalize_attachment_row({"file_id": value})
        if normalized:
            rows.append(normalized)

    attach_latest_raw = params.get("attach_latest_report_pdf")
    if attach_latest_raw is None:
        attach_latest = False
    else:
        attach_latest = _truthy(attach_latest_raw)
    if attach_latest:
        latest_pdf_path = str(context.settings.get("__latest_report_pdf_path") or "").strip()
        latest_document_id = str(context.settings.get("__latest_report_document_id") or "").strip()
        if latest_pdf_path:
            rows.append(
                {
                    "local_path": latest_pdf_path,
                    "label": str(context.settings.get("__latest_report_title") or latest_pdf_path).strip()
                    or latest_pdf_path,
                }
            )
        elif latest_document_id:
            rows.append(
                {
                    "file_id": latest_document_id,
                    "label": str(context.settings.get("__latest_report_title") or latest_document_id).strip()
                    or latest_document_id,
                }
            )

    return _dedupe_attachments(rows)


def _attachment_data(row: dict[str, str]) -> dict[str, str]:
    local_path = str(row.get("local_path") or "").strip()
    file_id = str(row.get("file_id") or "").strip()
    payload = {"attachment_label": str(row.get("label") or local_path or file_id).strip()}
    if local_path:
        payload["local_path"] = local_path
    if file_id:
        payload["file_id"] = file_id
    return payload


def _attach_to_gmail_draft(
    *,
    connector: Any,
    draft_id: str,
    attachments: list[dict[str, str]],
    trace_events: list[ToolTraceEvent],
) -> Generator[ToolTraceEvent, None, list[str]]:
    labels: list[str] = []
    if not attachments:
        return labels
    if not draft_id:
        raise ToolExecutionError("Draft ID is required before adding attachments.")
    for index, row in enumerate(attachments, start=1):
        payload = _attachment_data(row)
        detail = _compact_text(payload.get("attachment_label"), limit=160)
        attach_event = ToolTraceEvent(
            event_type="email_add_attachment",
            title=f"Attach file {index}/{len(attachments)}",
            detail=detail,
            data={"draft_id": draft_id, "index": index, "total": len(attachments), **payload},
        )
        trace_events.append(attach_event)
        yield attach_event

        local_path = str(row.get("local_path") or "").strip() or None
        file_id = str(row.get("file_id") or "").strip() or None
        connector.add_attachment(
            draft_id=draft_id,
            file_id=file_id,
            local_path=local_path,
        )
        labels.append(payload.get("attachment_label") or local_path or file_id or f"attachment-{index}")
    return labels
