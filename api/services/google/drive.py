from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.services.google.auth import GoogleAuthSession
from api.services.google.errors import GoogleApiError
from api.services.google.events import emit_google_event


class GoogleDriveService:
    def __init__(self, *, session: GoogleAuthSession) -> None:
        self.session = session

    def list_files(self, *, query: str = "", page_size: int = 50) -> dict[str, Any]:
        params: dict[str, Any] = {"pageSize": max(1, min(int(page_size), 1000))}
        if query:
            params["q"] = query
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.list_started",
            message="Listing Google Drive files",
            data={"query": query, "page_size": params["pageSize"]},
        )
        response = self.session.request_json(
            method="GET",
            url="https://www.googleapis.com/drive/v3/files",
            params=params,
        )
        files = response.get("files")
        count = len(files) if isinstance(files, list) else 0
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.list_completed",
            message="Google Drive files listed",
            data={"count": count},
        )
        return {
            "files": files if isinstance(files, list) else [],
            "next_page_token": response.get("nextPageToken"),
        }

    def create_folder(self, *, name: str, parent_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name.strip(),
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            payload["parents"] = [parent_id]
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.folder_creating",
            message="Creating Drive folder",
            data={"name": payload["name"]},
        )
        response = self.session.request_json(
            method="POST",
            url="https://www.googleapis.com/drive/v3/files",
            payload=payload,
        )
        folder_id = str(response.get("id") or "")
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.folder_created",
            message="Drive folder created",
            data={"folder_id": folder_id, "name": payload["name"]},
        )
        return {"folder_id": folder_id, "name": payload["name"]}

    def upload_file(self, *, local_path: str, folder_id: str | None = None) -> dict[str, Any]:
        path = Path(local_path)
        if not path.exists() or not path.is_file():
            raise GoogleApiError(
                code="drive_file_missing",
                message=f"Local file was not found: {local_path}",
                status_code=400,
            )
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        return self.upload_bytes(
            name=path.name,
            content_bytes=data,
            mime_type=mime_type,
            folder_id=folder_id,
        )

    def upload_bytes(
        self,
        *,
        name: str,
        content_bytes: bytes,
        mime_type: str,
        folder_id: str | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {"name": name}
        if folder_id:
            metadata["parents"] = [folder_id]
        boundary = "maia_drive_upload_boundary"
        metadata_part = json.dumps(metadata).encode("utf-8")
        body = (
            b"--"
            + boundary.encode("ascii")
            + b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            + metadata_part
            + b"\r\n--"
            + boundary.encode("ascii")
            + b"\r\nContent-Type: "
            + mime_type.encode("utf-8")
            + b"\r\n\r\n"
            + content_bytes
            + b"\r\n--"
            + boundary.encode("ascii")
            + b"--"
        )
        headers = {
            "Authorization": f"Bearer {self.session.require_access_token()}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        }
        request = Request(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            data=body,
            method="POST",
            headers=headers,
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.upload_started",
            message="Uploading file to Drive",
            data={"name": name, "size_bytes": len(content_bytes)},
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.upload_progress",
            message="Drive upload in progress",
            data={"name": name, "percent": 15},
        )
        try:
            with urlopen(request, timeout=60) as response:
                emit_google_event(
                    user_id=self.session.user_id,
                    run_id=self.session.run_id,
                    event_type="drive.upload_progress",
                    message="Drive upload in progress",
                    data={"name": name, "percent": 75},
                )
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise GoogleApiError(
                code="drive_upload_failed",
                message=f"Drive upload failed: {detail[:240]}",
                status_code=exc.code if 400 <= exc.code <= 599 else 502,
            ) from exc
        except Exception as exc:
            raise GoogleApiError(
                code="drive_upload_failed",
                message=f"Drive upload failed: {exc}",
                status_code=502,
            ) from exc
        if not isinstance(payload, dict):
            raise GoogleApiError(
                code="drive_upload_invalid_payload",
                message="Drive upload returned invalid payload.",
                status_code=502,
            )
        file_id = str(payload.get("id") or "")
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.upload_completed",
            message="Drive file uploaded",
            data={"file_id": file_id, "name": name},
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.upload_progress",
            message="Drive upload completed",
            data={"name": name, "percent": 100, "file_id": file_id},
        )
        return {"file_id": file_id, "name": name, "mime_type": mime_type}

    def share_file(self, *, file_id: str, email: str, role: str = "reader") -> dict[str, Any]:
        payload = {
            "type": "user",
            "role": role,
            "emailAddress": email,
        }
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.share_started",
            message="Sharing Drive file",
            data={"file_id": file_id, "email": email, "role": role},
        )
        self.session.request_json(
            method="POST",
            url=f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
            params={"sendNotificationEmail": "false"},
            payload=payload,
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.share_completed",
            message="Drive file shared",
            data={"file_id": file_id, "email": email, "role": role},
        )
        return {"ok": True, "file_id": file_id, "email": email, "role": role}

    def download_file(self, *, file_id: str) -> bytes:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.download_started",
            message="Downloading Drive file",
            data={"file_id": file_id},
        )
        content = self.session.request_bytes(
            method="GET",
            url=f"https://www.googleapis.com/drive/v3/files/{file_id}",
            params={"alt": "media"},
            timeout=60,
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="drive.download_completed",
            message="Drive file downloaded",
            data={"file_id": file_id, "size_bytes": len(content)},
        )
        return content

    def export_pdf_bytes(self, *, file_id: str) -> bytes:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.export_started",
            message="Exporting Google Doc as PDF",
            data={"file_id": file_id},
        )
        content = self.session.request_bytes(
            method="GET",
            url=f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
            params={"mimeType": "application/pdf"},
            timeout=60,
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="docs.export_completed",
            message="Google Doc exported as PDF",
            data={"file_id": file_id, "size_bytes": len(content)},
        )
        return content
