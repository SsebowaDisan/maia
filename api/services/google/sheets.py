from __future__ import annotations

from typing import Any

from api.services.google.auth import GoogleAuthSession
from api.services.google.events import emit_google_event


class GoogleSheetsService:
    def __init__(self, *, session: GoogleAuthSession) -> None:
        self.session = session

    def create_spreadsheet(self, *, title: str, sheet_title: str = "Tracker") -> dict[str, Any]:
        clean_title = str(title or "").strip() or "Maia Tracker"
        clean_sheet_title = str(sheet_title or "").strip() or "Tracker"
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="sheets.create_started",
            message="Creating Google Spreadsheet",
            data={"title": clean_title, "sheet_title": clean_sheet_title},
        )
        payload = {
            "properties": {"title": clean_title},
            "sheets": [{"properties": {"title": clean_sheet_title}}],
        }
        response = self.session.request_json(
            method="POST",
            url="https://sheets.googleapis.com/v4/spreadsheets",
            payload=payload,
        )
        spreadsheet_id = str(response.get("spreadsheetId") or "") if isinstance(response, dict) else ""
        spreadsheet_url = (
            str(response.get("spreadsheetUrl") or "") if isinstance(response, dict) else ""
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="sheets.create_completed",
            message="Google Spreadsheet created",
            data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
        )
        return {
            "spreadsheet_id": spreadsheet_id,
            "spreadsheet_url": spreadsheet_url,
            "title": clean_title,
            "sheet_title": clean_sheet_title,
        }

    def read_range(self, *, spreadsheet_id: str, a1_range: str) -> dict[str, Any]:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="sheets.read_started",
            message="Reading Google Sheets range",
            data={"spreadsheet_id": spreadsheet_id, "range": a1_range},
        )
        response = self.session.request_json(
            method="GET",
            url=f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{a1_range}",
        )
        values = response.get("values")
        rows = values if isinstance(values, list) else []
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="sheets.read_completed",
            message="Google Sheets range loaded",
            data={"spreadsheet_id": spreadsheet_id, "range": a1_range, "rows": len(rows)},
        )
        return {"values": rows}

    def append_rows(
        self,
        *,
        spreadsheet_id: str,
        a1_range: str,
        rows: list[list[Any]],
    ) -> dict[str, Any]:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="sheets.append_started",
            message="Appending rows to Google Sheets",
            data={"spreadsheet_id": spreadsheet_id, "range": a1_range, "rows": len(rows)},
        )
        response = self.session.request_json(
            method="POST",
            url=f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{a1_range}:append",
            params={"valueInputOption": "USER_ENTERED"},
            payload={"values": rows},
        )
        updates = dict(response.get("updates") or {}) if isinstance(response, dict) else {}
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="sheets.append_completed",
            message="Rows appended to Google Sheets",
            data={
                "spreadsheet_id": spreadsheet_id,
                "range": a1_range,
                "updated_rows": updates.get("updatedRows", 0),
            },
        )
        return {"update_info": updates}

    def update_range(
        self,
        *,
        spreadsheet_id: str,
        a1_range: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="sheets.update_started",
            message="Updating Google Sheets range",
            data={"spreadsheet_id": spreadsheet_id, "range": a1_range, "rows": len(values)},
        )
        response = self.session.request_json(
            method="PUT",
            url=f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{a1_range}",
            params={"valueInputOption": "USER_ENTERED"},
            payload={"values": values},
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="sheets.update_completed",
            message="Google Sheets range updated",
            data={"spreadsheet_id": spreadsheet_id, "range": a1_range},
        )
        return {"update_info": response}
