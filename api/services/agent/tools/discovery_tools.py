from __future__ import annotations

from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)


class LocalDiscoveryTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="marketing.local_discovery",
        action_class="read",
        risk_level="medium",
        required_permissions=["maps.read"],
        execution_policy="auto_execute",
        description="Discover companies via Google Places with geocoding and optional distance.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        query = str(params.get("query") or prompt).strip()
        if not query:
            raise ToolExecutionError("A discovery query is required.")

        origin = str(params.get("origin_address") or "").strip()
        connector = get_connector_registry().build("google_maps", settings=context.settings)
        places = connector.places_text_search(query=query)
        rows = places.get("results") if isinstance(places, dict) else []
        if not isinstance(rows, list):
            rows = []

        sources: list[AgentSource] = []
        lines: list[str] = [f"### Local discovery for: {query}"]
        destination_addresses: list[str] = []
        for row in rows[:8]:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "Business")
            formatted = str(row.get("formatted_address") or "")
            website = str(row.get("website") or "")
            rating = row.get("rating")
            lines.append(
                f"- {name} | {formatted or 'Address unavailable'}"
                + (f" | rating {rating}" if rating is not None else "")
            )
            if website:
                sources.append(
                    AgentSource(
                        source_type="web",
                        label=name,
                        url=website,
                        score=0.68,
                        metadata={"provider": "google_places"},
                    )
                )
            destination_addresses.append(formatted or name)

        distance_summary = ""
        if origin and destination_addresses:
            matrix = connector.distance_matrix(
                origins=[origin],
                destinations=destination_addresses[:5],
            )
            rows_matrix = matrix.get("rows") if isinstance(matrix, dict) else []
            if isinstance(rows_matrix, list) and rows_matrix:
                first = rows_matrix[0] if isinstance(rows_matrix[0], dict) else {}
                elements = first.get("elements") if isinstance(first, dict) else []
                if isinstance(elements, list):
                    parts: list[str] = []
                    for idx, element in enumerate(elements[:5]):
                        if not isinstance(element, dict):
                            continue
                        distance = (
                            ((element.get("distance") or {}).get("text"))
                            if isinstance(element.get("distance"), dict)
                            else ""
                        )
                        if distance:
                            parts.append(f"{idx + 1}. {distance}")
                    if parts:
                        distance_summary = "Estimated distances from origin: " + " | ".join(parts)

        if distance_summary:
            lines.append("")
            lines.append(distance_summary)

        return ToolExecutionResult(
            summary=f"Found {min(len(rows), 8)} local business result(s).",
            content="\n".join(lines),
            data={
                "query": query,
                "count": min(len(rows), 8),
                "origin_address": origin or None,
            },
            sources=sources,
            next_steps=[
                "Select top candidates and run website inspection workflow.",
                "Trigger personalized outreach draft for highest-fit companies.",
            ],
            events=[
                ToolTraceEvent(
                    event_type="web_search_started",
                    title="Search Google Places",
                    detail=query,
                    data={"query": query},
                ),
                ToolTraceEvent(
                    event_type="browser_extract",
                    title="Extract local business results",
                    detail=f"Captured {min(len(rows), 8)} result(s)",
                    data={"count": min(len(rows), 8)},
                ),
            ],
        )

