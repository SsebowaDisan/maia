from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.business_workflow_helpers import email_from_text


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
        from api.services.agent.tools import business_workflow_tools as workflow_tools_module

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
        api_hub = workflow_tools_module.get_connector_registry().build("google_api_hub", settings=context.settings)
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
        gmail = workflow_tools_module.get_connector_registry().build("gmail", settings=context.settings)
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
