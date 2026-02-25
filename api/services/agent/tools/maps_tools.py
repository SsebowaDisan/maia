from __future__ import annotations

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


class MapsGeocodeTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="maps.geocode",
        action_class="read",
        risk_level="low",
        required_permissions=["maps.read"],
        execution_policy="auto_execute",
        description="Geocode an address using Google Geocoding API.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        address = str(params.get("address") or prompt).strip()
        if not address:
            raise ToolExecutionError("`address` is required for geocoding.")
        connector = get_connector_registry().build("google_maps", settings=context.settings)
        payload = connector.geocode(address=address)
        results = payload.get("results") if isinstance(payload, dict) else []
        if not isinstance(results, list):
            results = []

        lines = [f"### Geocode results for: {address}"]
        for row in results[:5]:
            if not isinstance(row, dict):
                continue
            formatted = str(row.get("formatted_address") or "")
            geometry = row.get("geometry") or {}
            location = geometry.get("location") if isinstance(geometry, dict) else {}
            lat = location.get("lat") if isinstance(location, dict) else ""
            lng = location.get("lng") if isinstance(location, dict) else ""
            lines.append(f"- {formatted or 'address'} | lat={lat} lng={lng}")
        if len(lines) == 1:
            lines.append("- No geocode result.")

        return ToolExecutionResult(
            summary=f"Geocoding returned {len(results)} result(s).",
            content="\n".join(lines),
            data={"address": address, "count": len(results), "results": results[:5]},
            sources=[],
            next_steps=["Use coordinates in distance or local-discovery workflows."],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Geocode address",
                    detail=address,
                    data={"count": len(results)},
                )
            ],
        )


class MapsDistanceTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="maps.distance_matrix",
        action_class="read",
        risk_level="low",
        required_permissions=["maps.read"],
        execution_policy="auto_execute",
        description="Compute travel distance and duration via Google Distance Matrix API.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        origins = params.get("origins")
        destinations = params.get("destinations")
        if not isinstance(origins, list) or not origins:
            raise ToolExecutionError("`origins` must be a non-empty list.")
        if not isinstance(destinations, list) or not destinations:
            raise ToolExecutionError("`destinations` must be a non-empty list.")
        mode = str(params.get("mode") or "driving").strip()

        origin_rows = [str(item).strip() for item in origins if str(item).strip()]
        destination_rows = [str(item).strip() for item in destinations if str(item).strip()]
        connector = get_connector_registry().build("google_maps", settings=context.settings)
        payload = connector.distance_matrix(
            origins=origin_rows,
            destinations=destination_rows,
            mode=mode,
        )
        rows = payload.get("rows") if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            rows = []

        lines = [
            f"### Distance matrix ({mode})",
            f"- Origins: {', '.join(origin_rows)}",
            f"- Destinations: {', '.join(destination_rows)}",
        ]
        if rows:
            first = rows[0] if isinstance(rows[0], dict) else {}
            elements = first.get("elements") if isinstance(first, dict) else []
            if isinstance(elements, list):
                lines.append("")
                lines.append("### Results")
                for idx, element in enumerate(elements[: len(destination_rows)]):
                    if not isinstance(element, dict):
                        continue
                    distance = (
                        (element.get("distance") or {}).get("text")
                        if isinstance(element.get("distance"), dict)
                        else "n/a"
                    )
                    duration = (
                        (element.get("duration") or {}).get("text")
                        if isinstance(element.get("duration"), dict)
                        else "n/a"
                    )
                    target = destination_rows[idx] if idx < len(destination_rows) else f"destination {idx + 1}"
                    lines.append(f"- {target}: {distance}, {duration}")

        return ToolExecutionResult(
            summary=f"Computed distance matrix for {len(origin_rows)}x{len(destination_rows)} routes.",
            content="\n".join(lines),
            data={"origins": origin_rows, "destinations": destination_rows, "mode": mode},
            sources=[],
            next_steps=["Use route data to prioritize nearest high-fit accounts."],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Compute distance matrix",
                    detail=f"{len(origin_rows)}x{len(destination_rows)} routes",
                )
            ],
        )

