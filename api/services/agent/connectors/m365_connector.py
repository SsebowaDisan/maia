from __future__ import annotations

from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth


class M365Connector(BaseConnector):
    connector_id = "m365"

    def _token(self) -> str:
        token = self._read_secret("M365_ACCESS_TOKEN")
        if not token:
            raise ConnectorError("M365_ACCESS_TOKEN is not configured.")
        return token

    def health_check(self) -> ConnectorHealth:
        try:
            self._token()
        except ConnectorError as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    def list_onedrive_items(self, drive_id: str, root_item_id: str = "root") -> dict[str, Any]:
        token = self._token()
        return self.request_json(
            method="GET",
            url=f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{root_item_id}/children",
            headers={"Authorization": f"Bearer {token}"},
        )

    def append_excel_rows(
        self,
        *,
        drive_id: str,
        item_id: str,
        worksheet_name: str,
        table_name: str,
        rows: list[list[Any]],
    ) -> dict[str, Any]:
        token = self._token()
        return self.request_json(
            method="POST",
            url=(
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
                f"/workbook/tables/{table_name}/rows/add"
            ),
            headers={"Authorization": f"Bearer {token}"},
            payload={"values": rows},
        )
