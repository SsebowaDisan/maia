from __future__ import annotations

import re
from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


class EmailValidationTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="email.validate",
        action_class="read",
        risk_level="low",
        required_permissions=["email.validate"],
        execution_policy="auto_execute",
        description="Validate email deliverability via configured verification API.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        email = str(params.get("email") or "").strip()
        if not email:
            match = EMAIL_RE.search(prompt)
            email = match.group(0) if match else ""
        if not email:
            raise ToolExecutionError("Provide an email address to validate.")

        connector = get_connector_registry().build("email_validation", settings=context.settings)
        result = connector.validate(email=email)

        deliverability = str(
            result.get("deliverability")
            or result.get("status")
            or result.get("sub_status")
            or "unknown"
        )
        quality = str(result.get("quality_score") or result.get("qualityScore") or "")
        is_valid_format = result.get("is_valid_format")
        format_ok = (
            bool((is_valid_format or {}).get("value"))
            if isinstance(is_valid_format, dict)
            else bool(is_valid_format)
        )

        return ToolExecutionResult(
            summary=f"Validated email `{email}` ({deliverability}).",
            content=(
                f"Email validation result for `{email}`:\n"
                f"- Deliverability: {deliverability}\n"
                f"- Quality score: {quality or 'n/a'}\n"
                f"- Format valid: {'yes' if format_ok else 'unknown/no'}"
            ),
            data={"email": email, "deliverability": deliverability, "quality_score": quality},
            sources=[],
            next_steps=["Exclude risky addresses before campaign send."],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Validate email address",
                    detail=email,
                    data={"deliverability": deliverability},
                )
            ],
        )

