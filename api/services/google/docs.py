from __future__ import annotations

import re
from typing import Any

from api.services.google.auth import GoogleAuthSession
from api.services.google.drive import GoogleDriveService
from api.services.google.events import emit_google_event


class GoogleDocsService:
    def __init__(self, *, session: GoogleAuthSession) -> None:
        self.session = session
        self.drive = GoogleDriveService(session=session)

    @staticmethod
    def _document_end_index(document_payload: dict[str, Any]) -> int:
        body = document_payload.get("body")
        if not isinstance(body, dict):
            return 1
        content = body.get("content")
        if not isinstance(content, list):
            return 1
        for row in reversed(content):
            if not isinstance(row, dict):
                continue
            end_index = row.get("endIndex")
            if isinstance(end_index, int) and end_index > 1:
                return end_index - 1
        return 1

    @staticmethod
    def _strip_line_markdown(line: str) -> tuple[str, str, str]:
        text = str(line or "")
        heading_match = re.match(r"^(#{1,3})\s+(.*)$", text)
        if heading_match:
            hashes = heading_match.group(1)
            body = heading_match.group(2)
            style = {
                1: "HEADING_1",
                2: "HEADING_2",
                3: "HEADING_3",
            }.get(len(hashes), "NORMAL_TEXT")
            return body, style, ""

        bullet_match = re.match(r"^\s*[-*]\s+(.*)$", text)
        if bullet_match:
            return bullet_match.group(1), "NORMAL_TEXT", "BULLET_DISC_CIRCLE_SQUARE"

        numbered_match = re.match(r"^\s*\d+\.\s+(.*)$", text)
        if numbered_match:
            return numbered_match.group(1), "NORMAL_TEXT", "NUMBERED_DECIMAL_NESTED"

        return text, "NORMAL_TEXT", ""

    @staticmethod
    def _render_inline_markdown(text: str) -> tuple[str, list[tuple[int, int, str]]]:
        clean = str(text or "")
        pattern = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
        cursor = 0
        chunks: list[str] = []
        links: list[tuple[int, int, str]] = []
        out_len = 0
        for match in pattern.finditer(clean):
            start, end = match.span()
            if start > cursor:
                before = clean[cursor:start]
                chunks.append(before)
                out_len += len(before)
            label = str(match.group(1) or "").strip()
            url = str(match.group(2) or "").strip()
            if label and url:
                chunks.append(label)
                link_start = out_len
                out_len += len(label)
                links.append((link_start, out_len, url))
            else:
                raw = clean[start:end]
                chunks.append(raw)
                out_len += len(raw)
            cursor = end
        if cursor < len(clean):
            tail = clean[cursor:]
            chunks.append(tail)
            out_len += len(tail)
        return "".join(chunks), links

    @classmethod
    def _build_markdown_requests(
        cls,
        *,
        markdown_text: str,
        insert_index: int,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = str(markdown_text or "").splitlines()
        if not rows:
            rows = [""]

        full_text_parts: list[str] = []
        paragraph_styles: list[tuple[int, int, str]] = []
        bullet_ranges: list[tuple[int, int, str]] = []
        link_ranges: list[tuple[int, int, str]] = []
        char_cursor = 0

        for raw_row in rows:
            line_text, style, bullet_preset = cls._strip_line_markdown(raw_row)
            rendered_line, inline_links = cls._render_inline_markdown(line_text)

            line_start = char_cursor
            full_text_parts.append(rendered_line)
            char_cursor += len(rendered_line)
            line_end = char_cursor
            full_text_parts.append("\n")
            char_cursor += 1

            absolute_start = insert_index + line_start
            absolute_end = insert_index + line_end
            absolute_end_with_newline = absolute_end + 1

            if rendered_line.strip() and style != "NORMAL_TEXT":
                paragraph_styles.append((absolute_start, absolute_end_with_newline, style))
            if rendered_line.strip() and bullet_preset:
                bullet_ranges.append((absolute_start, absolute_end_with_newline, bullet_preset))
            for local_start, local_end, url in inline_links:
                link_ranges.append(
                    (
                        absolute_start + local_start,
                        absolute_start + local_end,
                        url,
                    )
                )

        full_text = "".join(full_text_parts)
        inserted_chars = len(full_text)
        if inserted_chars <= 0:
            return ([], 0)

        requests: list[dict[str, Any]] = [
            {
                "insertText": {
                    "location": {"index": insert_index},
                    "text": full_text,
                }
            }
        ]

        for start, end, style in paragraph_styles:
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "paragraphStyle": {"namedStyleType": style},
                        "fields": "namedStyleType",
                    }
                }
            )

        for start, end, bullet_preset in bullet_ranges:
            requests.append(
                {
                    "createParagraphBullets": {
                        "range": {"startIndex": start, "endIndex": end},
                        "bulletPreset": bullet_preset,
                    }
                }
            )

        for start, end, url in link_ranges:
            requests.append(
                {
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {"link": {"url": url}},
                        "fields": "link",
                    }
                }
            )

        return requests, inserted_chars

    def copy_template(self, *, template_file_id: str, title: str) -> dict[str, Any]:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.copy_started",
            message="Copying Google Docs template",
            data={"template_file_id": template_file_id, "title": title},
        )
        response = self.session.request_json(
            method="POST",
            url=f"https://www.googleapis.com/drive/v3/files/{template_file_id}/copy",
            payload={"name": title},
        )
        doc_id = str(response.get("id") or "")
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit" if doc_id else ""
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.copy_completed",
            message="Google Docs template copied",
            data={"doc_id": doc_id, "title": title, "source_url": doc_url},
        )
        return {"doc_id": doc_id, "title": title, "doc_url": doc_url}

    def create_document(self, *, title: str) -> dict[str, Any]:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.create_started",
            message="Creating Google Doc",
            data={"title": title},
        )
        response = self.session.request_json(
            method="POST",
            url="https://docs.googleapis.com/v1/documents",
            payload={"title": title},
        )
        doc_id = str(response.get("documentId") or "")
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit" if doc_id else ""
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.create_completed",
            message="Google Doc created",
            data={"doc_id": doc_id, "title": title, "source_url": doc_url},
        )
        return {"doc_id": doc_id, "title": title, "doc_url": doc_url}

    def replace_placeholders(self, *, doc_id: str, mapping: dict[str, str]) -> dict[str, Any]:
        requests = []
        for key in sorted(mapping.keys()):
            requests.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": key,
                            "matchCase": True,
                        },
                        "replaceText": str(mapping[key]),
                    }
                }
            )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.replace_started",
            message="Replacing placeholders in Google Doc",
            data={"doc_id": doc_id, "count": len(requests)},
        )
        self.session.request_json(
            method="POST",
            url=f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
            payload={"requests": requests},
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.replace_completed",
            message="Placeholder replacement completed",
            data={"doc_id": doc_id, "count": len(requests)},
        )
        return {"ok": True, "doc_id": doc_id, "replacements": len(requests)}

    def insert_text(self, *, doc_id: str, text: str) -> dict[str, Any]:
        safe_text = str(text or "")
        if not safe_text:
            return {"ok": True, "doc_id": doc_id, "inserted_chars": 0, "index": 1}

        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.insert_started",
            message="Appending text to Google Doc",
            data={"doc_id": doc_id, "characters": len(safe_text)},
        )
        document_payload = self.session.request_json(
            method="GET",
            url=f"https://docs.googleapis.com/v1/documents/{doc_id}",
            params={"fields": "body/content/endIndex"},
        )
        insert_index = self._document_end_index(
            document_payload if isinstance(document_payload, dict) else {}
        )
        self.session.request_json(
            method="POST",
            url=f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
            payload={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": insert_index},
                            "text": safe_text,
                        }
                    }
                ]
            },
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.insert_completed",
            message="Text appended to Google Doc",
            data={"doc_id": doc_id, "characters": len(safe_text), "index": insert_index},
        )
        return {
            "ok": True,
            "doc_id": doc_id,
            "inserted_chars": len(safe_text),
            "index": insert_index,
        }

    def insert_markdown(self, *, doc_id: str, markdown_text: str) -> dict[str, Any]:
        safe_text = str(markdown_text or "")
        if not safe_text:
            return {"ok": True, "doc_id": doc_id, "inserted_chars": 0, "index": 1}

        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.insert_started",
            message="Appending markdown to Google Doc",
            data={"doc_id": doc_id, "characters": len(safe_text), "render_mode": "markdown"},
        )
        document_payload = self.session.request_json(
            method="GET",
            url=f"https://docs.googleapis.com/v1/documents/{doc_id}",
            params={"fields": "body/content/endIndex"},
        )
        insert_index = self._document_end_index(
            document_payload if isinstance(document_payload, dict) else {}
        )
        requests, inserted_chars = self._build_markdown_requests(
            markdown_text=safe_text,
            insert_index=insert_index,
        )
        if inserted_chars <= 0 or not requests:
            return {"ok": True, "doc_id": doc_id, "inserted_chars": 0, "index": insert_index}
        self.session.request_json(
            method="POST",
            url=f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
            payload={"requests": requests},
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.insert_completed",
            message="Markdown appended to Google Doc",
            data={
                "doc_id": doc_id,
                "characters": inserted_chars,
                "index": insert_index,
                "render_mode": "markdown",
            },
        )
        return {
            "ok": True,
            "doc_id": doc_id,
            "inserted_chars": inserted_chars,
            "index": insert_index,
        }

    def get_document_text(self, *, doc_id: str) -> dict[str, Any]:
        """Fetch plain text content from a Google Doc."""
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.read_started",
            message="Reading Google Doc content",
            data={"doc_id": doc_id},
        )
        document = self.session.request_json(
            method="GET",
            url=f"https://docs.googleapis.com/v1/documents/{doc_id}",
        )
        title = str(document.get("title") or "") if isinstance(document, dict) else ""
        text_parts: list[str] = []
        body = document.get("body") if isinstance(document, dict) else None
        content = body.get("content") if isinstance(body, dict) else []
        for element in content if isinstance(content, list) else []:
            para = element.get("paragraph") if isinstance(element, dict) else None
            if not isinstance(para, dict):
                continue
            for pe in para.get("elements") or []:
                tr = pe.get("textRun") if isinstance(pe, dict) else None
                if isinstance(tr, dict):
                    raw = str(tr.get("content") or "")
                    if raw:
                        text_parts.append(raw)
        full_text = "".join(text_parts)
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.read_completed",
            message="Google Doc content loaded",
            data={"doc_id": doc_id, "chars": len(full_text), "source_url": doc_url},
        )
        return {"doc_id": doc_id, "title": title, "text": full_text, "doc_url": doc_url}

    def export_pdf(self, *, doc_id: str, folder_id: str | None = None) -> dict[str, Any]:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.export_started",
            message="Exporting Google Doc to PDF",
            data={"doc_id": doc_id},
        )
        pdf_bytes = self.drive.export_pdf_bytes(file_id=doc_id)
        uploaded = self.drive.upload_bytes(
            name=f"{doc_id}.pdf",
            content_bytes=pdf_bytes,
            mime_type="application/pdf",
            folder_id=folder_id,
        )
        file_id = str(uploaded.get("file_id") or "")
        source_url = f"https://drive.google.com/file/d/{file_id}/view" if file_id else ""
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.export_completed",
            message="Google Doc exported to PDF",
            data={"doc_id": doc_id, "drive_file_id": file_id, "source_url": source_url},
        )
        return {"drive_file_id": file_id, "doc_id": doc_id, "source_url": source_url}
