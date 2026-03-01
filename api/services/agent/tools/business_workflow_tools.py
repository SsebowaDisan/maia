from __future__ import annotations

from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.business_workflow_helpers import (
    email_from_text,
    read_destinations,
    route_from_prompt,
    safe_int,
)


class BusinessRoutePlanTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="business.route_plan",
        action_class="read",
        risk_level="low",
        required_permissions=["maps.read"],
        execution_policy="auto_execute",
        description="Create an easy route plan with travel time ranking and optional Sheets export.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        origin = str(params.get("origin") or params.get("start_location") or "").strip()
        destinations = read_destinations(params.get("destinations") or params.get("stops"))
        if not origin or not destinations:
            parsed_origin, parsed_destinations = route_from_prompt(prompt)
            origin = origin or parsed_origin
            if not destinations:
                destinations = parsed_destinations
        if not origin:
            raise ToolExecutionError("Provide `origin` (or phrase your prompt as `from <origin> to <destinations>`).")
        if not destinations:
            raise ToolExecutionError("Provide at least one destination (`destinations` or `stops`).")

        mode = str(params.get("mode") or "driving").strip().lower() or "driving"
        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="api_call_started",
                title="Compute route candidates",
                detail=f"{origin} -> {len(destinations)} destination(s)",
                data={
                    "tool_id": self.metadata.tool_id,
                    "scene_surface": "browser",
                    "api_name": "Distance Matrix API",
                },
            )
        ]
        maps_connector = get_connector_registry().build("google_maps", settings=context.settings)
        payload = maps_connector.distance_matrix(
            origins=[origin],
            destinations=destinations,
            mode=mode,
        )
        rows = payload.get("rows") if isinstance(payload, dict) else []
        first_row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
        elements = first_row.get("elements") if isinstance(first_row, dict) else []
        if not isinstance(elements, list):
            elements = []
        events.append(
            ToolTraceEvent(
                event_type="api_call_completed",
                title="Route candidates loaded",
                detail=f"{len(elements)} route entries",
                data={
                    "tool_id": self.metadata.tool_id,
                    "scene_surface": "browser",
                    "top_level_keys": sorted(list(payload.keys()))[:12] if isinstance(payload, dict) else [],
                },
            )
        )

        ranked: list[dict[str, Any]] = []
        for idx, destination in enumerate(destinations):
            element = elements[idx] if idx < len(elements) and isinstance(elements[idx], dict) else {}
            status = str(element.get("status") or "UNKNOWN")
            distance_obj = element.get("distance")
            duration_obj = element.get("duration")
            distance_text = str(distance_obj.get("text") or "") if isinstance(distance_obj, dict) else ""
            duration_text = str(duration_obj.get("text") or "") if isinstance(duration_obj, dict) else ""
            duration_value = safe_int(duration_obj.get("value") if isinstance(duration_obj, dict) else None, 10**9)
            ranked.append(
                {
                    "destination": destination,
                    "status": status,
                    "distance_text": distance_text or "n/a",
                    "duration_text": duration_text or "n/a",
                    "duration_value": duration_value,
                }
            )
        ranked.sort(key=lambda item: item.get("duration_value", 10**9))

        spreadsheet_id = str(params.get("spreadsheet_id") or "").strip()
        sheet_range = str(params.get("sheet_range") or "Tracker!A1").strip() or "Tracker!A1"
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit" if spreadsheet_id else ""
        if spreadsheet_id:
            rows_to_append: list[list[str]] = [
                ["Origin", "Destination", "Distance", "Duration", "Status", "Mode"],
            ]
            for row in ranked:
                rows_to_append.append(
                    [
                        origin,
                        str(row.get("destination") or ""),
                        str(row.get("distance_text") or "n/a"),
                        str(row.get("duration_text") or "n/a"),
                        str(row.get("status") or "UNKNOWN"),
                        mode,
                    ]
                )
            workspace_connector = get_connector_registry().build("google_workspace", settings=context.settings)
            events.extend(
                [
                    ToolTraceEvent(
                        event_type="sheet_open",
                        title="Open route plan tracker",
                        detail=spreadsheet_id,
                        data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
                    ),
                    ToolTraceEvent(
                        event_type="sheets.append_started",
                        title="Write route plan rows",
                        detail=f"{len(rows_to_append)} row(s)",
                        data={"spreadsheet_id": spreadsheet_id, "range": sheet_range, "source_url": spreadsheet_url},
                    ),
                    ToolTraceEvent(
                        event_type="sheet_append_row",
                        title="Append route plan payload",
                        detail=f"Range {sheet_range}",
                        data={"spreadsheet_id": spreadsheet_id, "sheet_range": sheet_range},
                    ),
                ]
            )
            append_response = workspace_connector.append_sheet_values(
                spreadsheet_id=spreadsheet_id,
                sheet_range=sheet_range,
                values=rows_to_append,
            )
            updated_rows = (
                (append_response.get("updates") or {}).get("updatedRows")
                if isinstance(append_response, dict)
                else 0
            )
            events.extend(
                [
                    ToolTraceEvent(
                        event_type="sheets.append_completed",
                        title="Route plan rows saved",
                        detail=f"Updated rows: {updated_rows or 0}",
                        data={"spreadsheet_id": spreadsheet_id, "updated_rows": updated_rows or 0, "source_url": spreadsheet_url},
                    ),
                    ToolTraceEvent(
                        event_type="sheet_save",
                        title="Save route tracker",
                        detail=spreadsheet_id,
                        data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
                    ),
                ]
            )

        lines = [
            f"### Route plan ({mode})",
            f"- Origin: {origin}",
            f"- Destinations: {len(destinations)}",
            "",
            "### Ranked by travel time",
        ]
        for row in ranked[:8]:
            lines.append(
                f"- {row['destination']}: {row['duration_text']} ({row['distance_text']}, status={row['status']})"
            )
        if spreadsheet_url:
            lines.extend(["", f"- Sheets tracker: {spreadsheet_url}"])

        return ToolExecutionResult(
            summary=f"Built route plan for {len(destinations)} destination(s).",
            content="\n".join(lines),
            data={
                "origin": origin,
                "destinations": destinations,
                "mode": mode,
                "ranked_routes": ranked,
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet_url": spreadsheet_url,
            },
            sources=[],
            next_steps=[
                "Use the top route for dispatch or customer visit planning.",
                "Share the route tracker link with operations if a sheet was provided.",
            ],
            events=events,
        )


class BusinessGa4KpiSheetReportTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="business.ga4_kpi_sheet_report",
        action_class="execute",
        risk_level="medium",
        required_permissions=["analytics.read", "sheets.write"],
        execution_policy="auto_execute",
        description="Generate a GA4 KPI summary and write it into Google Sheets.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        property_id = str(params.get("property_id") or "").strip() or None
        sheet_range = str(params.get("sheet_range") or "Tracker!A1").strip() or "Tracker!A1"
        spreadsheet_id = str(params.get("spreadsheet_id") or "").strip()
        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="api_call_started",
                title="Run GA4 KPI report",
                detail=str(property_id or "default property"),
                data={
                    "tool_id": self.metadata.tool_id,
                    "scene_surface": "system",
                    "api_name": "Google Analytics Data API",
                },
            )
        ]
        analytics = get_connector_registry().build("google_analytics", settings=context.settings)
        report = analytics.run_report(
            property_id=property_id,
            date_ranges=[{"startDate": "7daysAgo", "endDate": "today"}],
            dimensions=["date"],
            metrics=["sessions", "totalUsers", "conversions"],
            limit=20,
        )
        rows = report.get("rows") if isinstance(report, dict) else []
        row_count = len(rows) if isinstance(rows, list) else 0
        events.append(
            ToolTraceEvent(
                event_type="api_call_completed",
                title="GA4 KPI report loaded",
                detail=f"{row_count} row(s)",
                data={
                    "tool_id": self.metadata.tool_id,
                    "scene_surface": "system",
                    "top_level_keys": sorted(list(report.keys()))[:12] if isinstance(report, dict) else [],
                },
            )
        )

        workspace = get_connector_registry().build("google_workspace", settings=context.settings)
        spreadsheet_url = ""
        if not spreadsheet_id:
            title = str(params.get("title") or "Maia GA4 KPI Report").strip() or "Maia GA4 KPI Report"
            created = workspace.create_spreadsheet(title=title, sheet_title="Tracker")
            spreadsheet_id = str(created.get("spreadsheet_id") or "").strip()
            spreadsheet_url = str(created.get("spreadsheet_url") or "").strip()
        if not spreadsheet_id:
            raise ToolExecutionError("Unable to determine target spreadsheet for GA4 KPI report.")
        if not spreadsheet_url:
            spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

        sheet_rows: list[list[str]] = [["Date", "Sessions", "Users", "Conversions"]]
        for row in (rows if isinstance(rows, list) else [])[:20]:
            if not isinstance(row, dict):
                continue
            dims = row.get("dimensionValues") if isinstance(row.get("dimensionValues"), list) else []
            mets = row.get("metricValues") if isinstance(row.get("metricValues"), list) else []
            date_value = str((dims[0] or {}).get("value") or "") if len(dims) > 0 and isinstance(dims[0], dict) else ""
            sessions = str((mets[0] or {}).get("value") or "") if len(mets) > 0 and isinstance(mets[0], dict) else ""
            users = str((mets[1] or {}).get("value") or "") if len(mets) > 1 and isinstance(mets[1], dict) else ""
            conversions = str((mets[2] or {}).get("value") or "") if len(mets) > 2 and isinstance(mets[2], dict) else ""
            sheet_rows.append([date_value, sessions, users, conversions])

        events.extend(
            [
                ToolTraceEvent(
                    event_type="sheet_open",
                    title="Open GA4 KPI sheet",
                    detail=spreadsheet_id,
                    data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
                ),
                ToolTraceEvent(
                    event_type="sheets.append_started",
                    title="Write KPI rows",
                    detail=f"{len(sheet_rows)} row(s)",
                    data={"spreadsheet_id": spreadsheet_id, "range": sheet_range, "source_url": spreadsheet_url},
                ),
                ToolTraceEvent(
                    event_type="sheet_append_row",
                    title="Append GA4 KPI payload",
                    detail=sheet_range,
                    data={"spreadsheet_id": spreadsheet_id, "sheet_range": sheet_range},
                ),
            ]
        )
        append_response = workspace.append_sheet_values(
            spreadsheet_id=spreadsheet_id,
            sheet_range=sheet_range,
            values=sheet_rows,
        )
        updated_rows = (
            (append_response.get("updates") or {}).get("updatedRows")
            if isinstance(append_response, dict)
            else 0
        )
        events.extend(
            [
                ToolTraceEvent(
                    event_type="sheets.append_completed",
                    title="KPI rows saved",
                    detail=f"Updated rows: {updated_rows or 0}",
                    data={"spreadsheet_id": spreadsheet_id, "updated_rows": updated_rows or 0, "source_url": spreadsheet_url},
                ),
                ToolTraceEvent(
                    event_type="sheet_save",
                    title="Save KPI tracker sheet",
                    detail=spreadsheet_id,
                    data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
                ),
            ]
        )

        return ToolExecutionResult(
            summary=f"GA4 KPI report written to Sheets ({updated_rows or 0} updated rows).",
            content=(
                "### GA4 KPI report\n"
                f"- Rows fetched: {row_count}\n"
                f"- Spreadsheet: {spreadsheet_url}\n"
                f"- Sheet range: {sheet_range}"
            ),
            data={
                "row_count": row_count,
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet_url": spreadsheet_url,
                "sheet_range": sheet_range,
                "updated_rows": updated_rows or 0,
            },
            sources=[],
            next_steps=[
                "Share the KPI sheet with leadership.",
                "Schedule this workflow weekly using recurring task automation.",
            ],
            events=events,
        )


class BusinessCloudIncidentDigestEmailTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="business.cloud_incident_digest_email",
        action_class="execute",
        risk_level="high",
        required_permissions=["logging.read", "gmail.send"],
        execution_policy="confirm_before_execute",
        description="Summarize recent Cloud Logging incidents and deliver via email.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        recipient = str(params.get("to") or email_from_text(prompt)).strip()
        if not recipient:
            raise ToolExecutionError("Provide recipient email (`to`) for incident digest delivery.")
        project_id = str(params.get("project_id") or context.settings.get("GOOGLE_CLOUD_PROJECT") or "").strip()
        resource_names = params.get("resource_names")
        if isinstance(resource_names, list):
            names = [str(item).strip() for item in resource_names if str(item).strip()]
        elif project_id:
            names = [f"projects/{project_id}"]
        else:
            names = []
        if not names:
            raise ToolExecutionError("Provide `project_id` or `resource_names` for Cloud Logging query.")

        filter_text = str(
            params.get("filter")
            or 'severity>=ERROR timestamp>="2026-01-01T00:00:00Z"'
        ).strip()
        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="api_call_started",
                title="Fetch cloud incident logs",
                detail=", ".join(names[:2]),
                data={
                    "tool_id": self.metadata.tool_id,
                    "scene_surface": "system",
                    "api_name": "Cloud Logging API",
                },
            )
        ]
        api_hub = get_connector_registry().build("google_api_hub", settings=context.settings)
        response = api_hub.call_json_api(
            base_url="https://logging.googleapis.com",
            path="v2/entries:list",
            method="POST",
            body={
                "resourceNames": names,
                "filter": filter_text,
                "pageSize": 20,
            },
            query={},
            auth_mode="oauth",
            api_key_envs=(),
        )
        entries = response.get("entries") if isinstance(response, dict) else []
        if not isinstance(entries, list):
            entries = []
        events.append(
            ToolTraceEvent(
                event_type="api_call_completed",
                title="Cloud incident logs loaded",
                detail=f"{len(entries)} entry(ies)",
                data={
                    "tool_id": self.metadata.tool_id,
                    "scene_surface": "system",
                    "top_level_keys": sorted(list(response.keys()))[:12] if isinstance(response, dict) else [],
                },
            )
        )

        severity_counts: dict[str, int] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            severity = str(entry.get("severity") or "UNKNOWN").upper()
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        lines = ["Cloud Incident Digest", "", "Severity Summary:"]
        for key in sorted(severity_counts.keys()):
            lines.append(f"- {key}: {severity_counts[key]}")
        if not severity_counts:
            lines.append("- No incidents returned for selected window.")
        lines.extend(["", "Top entries:"])
        for entry in entries[:5]:
            if not isinstance(entry, dict):
                continue
            severity = str(entry.get("severity") or "UNKNOWN")
            timestamp = str(entry.get("timestamp") or "")
            message = str(((entry.get("textPayload") or entry.get("jsonPayload") or "") or "")).strip()
            preview = " ".join(message.split())[:180] if message else "No payload preview."
            lines.append(f"- [{severity}] {timestamp} :: {preview}")
        body = "\n".join(lines)

        subject = str(params.get("subject") or "Cloud Incident Digest").strip() or "Cloud Incident Digest"
        send_now = bool(params.get("send", False))
        gmail = get_connector_registry().build("gmail", settings=context.settings)
        events.extend(
            [
                ToolTraceEvent(event_type="email_open_compose", title="Open incident digest email", detail=recipient),
                ToolTraceEvent(event_type="email_draft_create", title="Create incident digest draft", detail=recipient),
                ToolTraceEvent(event_type="email_set_to", title="Apply recipient", detail=recipient),
                ToolTraceEvent(event_type="email_set_subject", title="Apply subject", detail=subject),
                ToolTraceEvent(
                    event_type="email_set_body",
                    title="Compose incident digest body",
                    detail=f"{len(body)} characters",
                    data={"typed_preview": body[:160]},
                ),
            ]
        )
        if send_now:
            send_response = gmail.send_message(to=recipient, subject=subject, body=body)
            message_id = str(send_response.get("id") or "").strip()
            events.extend(
                [
                    ToolTraceEvent(event_type="email_click_send", title="Send incident digest", detail=recipient),
                    ToolTraceEvent(event_type="email_sent", title="Incident digest sent", detail=message_id or recipient),
                ]
            )
            summary = f"Cloud incident digest sent to {recipient}."
            next_steps = ["Review incident trends and define remediation actions."]
            delivery = {"sent": True, "message_id": message_id}
        else:
            draft_response = gmail.create_draft(to=recipient, subject=subject, body=body)
            draft_id = str((draft_response.get("draft") or {}).get("id") or "").strip()
            events.append(
                ToolTraceEvent(event_type="email_ready_to_send", title="Incident digest draft ready", detail=draft_id or recipient)
            )
            summary = f"Cloud incident digest draft created for {recipient}."
            next_steps = ["Review and send the draft when ready."]
            delivery = {"sent": False, "draft_id": draft_id}

        return ToolExecutionResult(
            summary=summary,
            content=body,
            data={
                "recipient": recipient,
                "subject": subject,
                "entry_count": len(entries),
                "severity_counts": severity_counts,
                "delivery": delivery,
            },
            sources=[],
            next_steps=next_steps,
            events=events,
        )
