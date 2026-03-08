from __future__ import annotations

import html
import re
from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)


class CompetitorProfileTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="marketing.competitor_profile",
        action_class="draft",
        risk_level="low",
        required_permissions=["analysis.write"],
        execution_policy="auto_execute",
        description="Build a concise competitor profile from provided context.",
    )

    _COMPETITOR_RE = re.compile(r"\b(versus|vs\.?|against)\s+([A-Za-z0-9 ._-]+)", re.IGNORECASE)

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        competitor = str(params.get("competitor") or "").strip()
        if not competitor:
            match = self._COMPETITOR_RE.search(prompt)
            if match:
                competitor = match.group(2).strip()
        if not competitor:
            competitor = "Competitor"

        positioning = params.get("positioning") or "Positioning is not yet validated."
        pricing = params.get("pricing") or "Pricing signals need verified source data."
        channels = params.get("channels") or "Channel mix unknown."

        content = (
            f"### Competitor Profile: {html.escape(competitor)}\n"
            f"- Positioning: {positioning}\n"
            f"- Pricing signals: {pricing}\n"
            f"- Distribution/marketing channels: {channels}\n"
            "- Key gap to exploit: emphasize measurable outcomes + faster execution."
        )
        return ToolExecutionResult(
            summary=f"Drafted competitor profile for {competitor}.",
            content=content,
            data={"competitor": competitor},
            sources=[],
            next_steps=[
                "Attach at least 3 verifiable sources for pricing and claims.",
                "Run messaging A/B draft recommendations.",
            ],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Assemble competitor profile",
                    detail=f"Structured profile generated for {competitor}",
                    data={"competitor": competitor},
                )
            ],
        )
