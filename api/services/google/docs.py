from __future__ import annotations

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
