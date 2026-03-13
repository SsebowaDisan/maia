from __future__ import annotations

from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth
from api.services.google.auth import GoogleAuthSession
from api.services.google.docs import GoogleDocsService
from api.services.google.drive import GoogleDriveService
from api.services.google.errors import GoogleServiceError
from api.services.google.oauth_scopes import connector_required_scopes
from api.services.google.sheets import GoogleSheetsService


class GoogleWorkspaceConnector(BaseConnector):
    connector_id = "google_workspace"

    def _session(self) -> GoogleAuthSession:
        user_id = str(self.settings.get("__agent_user_id") or self.settings.get("agent.tenant_id") or "default")
        run_id = str(self.settings.get("__agent_run_id") or "").strip() or None
        fallback = {
            "access_token": self._read_secret("GOOGLE_WORKSPACE_ACCESS_TOKEN"),
            "refresh_token": self._read_secret("GOOGLE_WORKSPACE_REFRESH_TOKEN"),
            "token_type": "Bearer",
        }
        return GoogleAuthSession(
            user_id=user_id,
            run_id=run_id,
            fallback_tokens=fallback,
            settings=self.settings,
        )

    def _token(self) -> str:
        token = self._session().require_access_token()
        if not token:
            raise ConnectorError("GOOGLE_WORKSPACE_ACCESS_TOKEN is not configured.")
        return token

    def _authorized_session(self) -> GoogleAuthSession:
        session = self._session()
        session.require_scopes(
            connector_required_scopes(self.connector_id),
            reason="Google Workspace access",
        )
        return session

    def health_check(self) -> ConnectorHealth:
        try:
            self._authorized_session().require_access_token()
        except (ConnectorError, GoogleServiceError) as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    def list_drive_files(self, query: str = "") -> dict[str, Any]:
        service = GoogleDriveService(session=self._authorized_session())
        try:
            return service.list_files(query=query, page_size=20)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def append_sheet_values(
        self,
        *,
        spreadsheet_id: str,
        sheet_range: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        service = GoogleSheetsService(session=self._authorized_session())
        try:
            result = service.append_rows(
                spreadsheet_id=spreadsheet_id,
                a1_range=sheet_range,
                rows=values,
            )
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        return {"updates": result.get("update_info") or {}}

    def create_docs_document(self, title: str) -> dict[str, Any]:
        service = GoogleDocsService(session=self._authorized_session())
        try:
            result = service.create_document(title=title)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        return {"documentId": result.get("doc_id") or ""}

    def docs_replace_text(
        self,
        *,
        document_id: str,
        replacements: dict[str, str],
    ) -> dict[str, Any]:
        service = GoogleDocsService(session=self._authorized_session())
        try:
            return service.replace_placeholders(doc_id=document_id, mapping=replacements)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def docs_insert_text(
        self,
        *,
        document_id: str,
        text: str,
    ) -> dict[str, Any]:
        service = GoogleDocsService(session=self._authorized_session())
        try:
            return service.insert_text(doc_id=document_id, text=text)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def docs_insert_markdown(
        self,
        *,
        document_id: str,
        markdown_text: str,
    ) -> dict[str, Any]:
        service = GoogleDocsService(session=self._authorized_session())
        try:
            return service.insert_markdown(doc_id=document_id, markdown_text=markdown_text)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def create_spreadsheet(
        self,
        *,
        title: str,
        sheet_title: str = "Tracker",
    ) -> dict[str, Any]:
        service = GoogleSheetsService(session=self._authorized_session())
        try:
            return service.create_spreadsheet(title=title, sheet_title=sheet_title)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def create_drive_folder(self, *, name: str, parent_id: str | None = None) -> dict[str, Any]:
        service = GoogleDriveService(session=self._authorized_session())
        try:
            result = service.create_folder(name=name, parent_id=parent_id)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        return {"id": result.get("folder_id") or "", "name": result.get("name") or name}

    def create_drive_text_file(
        self,
        *,
        name: str,
        content: str,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            service = GoogleDriveService(session=self._authorized_session())
            result = service.upload_bytes(
                name=name,
                content_bytes=content.encode("utf-8"),
                mime_type="text/plain",
                folder_id=parent_id,
            )
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        return {"id": result.get("file_id") or "", "name": result.get("name") or name}

    def share_drive_file(
        self,
        *,
        file_id: str,
        email: str,
        role: str = "reader",
    ) -> dict[str, Any]:
        service = GoogleDriveService(session=self._authorized_session())
        try:
            return service.share_file(file_id=file_id, email=email, role=role)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def share_drive_file_public(
        self,
        *,
        file_id: str,
        role: str = "reader",
        discoverable: bool = False,
    ) -> dict[str, Any]:
        service = GoogleDriveService(session=self._authorized_session())
        try:
            return service.share_file_public(
                file_id=file_id,
                role=role,
                discoverable=bool(discoverable),
            )
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def read_sheet_range(
        self,
        *,
        spreadsheet_id: str,
        sheet_range: str,
    ) -> dict[str, Any]:
        service = GoogleSheetsService(session=self._authorized_session())
        try:
            result = service.read_range(spreadsheet_id=spreadsheet_id, a1_range=sheet_range)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        return {
            "spreadsheet_id": spreadsheet_id,
            "sheet_range": sheet_range,
            "values": result.get("values") or [],
            "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        }

    def docs_read_text(self, *, document_id: str) -> dict[str, Any]:
        service = GoogleDocsService(session=self._authorized_session())
        try:
            return service.get_document_text(doc_id=document_id)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def delete_drive_file(self, *, file_id: str) -> dict[str, Any]:
        service = GoogleDriveService(session=self._authorized_session())
        try:
            return service.delete_file(file_id=file_id)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def rename_drive_file(self, *, file_id: str, name: str) -> dict[str, Any]:
        service = GoogleDriveService(session=self._authorized_session())
        try:
            return service.rename_file(file_id=file_id, name=name)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def export_drive_file_pdf(self, *, file_id: str) -> bytes:
        try:
            service = GoogleDriveService(session=self._authorized_session())
            return service.export_pdf_bytes(file_id=file_id)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
