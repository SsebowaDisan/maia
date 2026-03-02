from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.web_extract_tools import WebStructuredExtractTool

SCENE_SURFACE_PREVIEW = "preview"

ADAPTER_SCHEMAS: dict[str, dict[str, Any]] = {
    "linkedin_company": {
        "goal": "Extract public LinkedIn company profile signals for research.",
        "schema": {
            "company_name": "string",
            "industry": "string",
            "headquarters": "string",
            "employee_count": "string",
            "about_summary": "string",
        },
    },
    "reuters_article": {
        "goal": "Extract Reuters article facts and summary for evidence-based briefing.",
        "schema": {
            "headline": "string",
            "publish_date": "string",
            "author": "string",
            "summary": "string",
            "key_entities": "array",
            "key_claims": "array",
        },
    },
    "github_repository": {
        "goal": "Extract GitHub repository metadata and maintainability signals.",
        "schema": {
            "repo_name": "string",
            "owner": "string",
            "primary_language": "string",
            "stars": "integer",
            "forks": "integer",
            "last_updated": "string",
            "readme_summary": "string",
        },
    },
    "google_maps_reviews": {
        "goal": "Extract Google Maps place and review summary signals from public pages.",
        "schema": {
            "place_name": "string",
            "rating": "number",
            "review_count": "integer",
            "location": "string",
            "sentiment_summary": "string",
            "top_review_themes": "array",
        },
    },
    "generic_web_profile": {
        "goal": "Extract structured profile fields from a public web page.",
        "schema": {
            "title": "string",
            "summary": "string",
            "entities": "array",
            "claims": "array",
            "contacts": "array",
        },
    },
}


def _event(
    *,
    tool_id: str,
    event_type: str,
    title: str,
    detail: str = "",
    data: dict[str, Any] | None = None,
) -> ToolTraceEvent:
    payload = {"tool_id": tool_id, "scene_surface": SCENE_SURFACE_PREVIEW}
    if isinstance(data, dict):
        payload.update(data)
    return ToolTraceEvent(event_type=event_type, title=title, detail=detail, data=payload)


class WebDatasetAdapterTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="web.dataset.adapter",
        action_class="read",
        risk_level="medium",
        required_permissions=["web.read"],
        execution_policy="auto_execute",
        description="Run domain adapter extraction for priority web datasets.",
    )

    def _choose_adapter(
        self,
        *,
        url: str,
        goal: str,
        requested_adapter: str,
    ) -> tuple[str, bool, float, str]:
        if requested_adapter in ADAPTER_SCHEMAS:
            return requested_adapter, False, 1.0, "Adapter was provided explicitly."
        payload = {
            "url": url,
            "goal": goal,
            "allowed_adapters": list(ADAPTER_SCHEMAS.keys()),
        }
        response = call_json_response(
            system_prompt=(
                "Select the best adapter for structured web extraction. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Pick exactly one adapter from allowed_adapters for this request.\n"
                "Return JSON: "
                "{\"adapter\": \"adapter_name\", \"confidence\": 0.0, \"reason\": \"short reason\"}\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=180,
        )
        adapter = (
            str(response.get("adapter") or "").strip()
            if isinstance(response, dict)
            else ""
        )
        try:
            confidence = max(0.0, min(1.0, float(response.get("confidence") or 0.0))) if isinstance(response, dict) else 0.0
        except Exception:
            confidence = 0.0
        reason = " ".join(str(response.get("reason") or "").split()).strip()[:220] if isinstance(response, dict) else ""
        if adapter not in ADAPTER_SCHEMAS:
            return "generic_web_profile", True, max(0.35, confidence), reason or "No valid adapter returned by LLM."
        return adapter, True, confidence, reason or "Adapter selected by LLM."

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        tool_id = self.metadata.tool_id
        url = str(params.get("url") or "").strip()
        page_text = str(params.get("page_text") or "").strip()
        goal = str(params.get("goal") or params.get("extraction_goal") or prompt).strip()
        requested_adapter = str(params.get("adapter") or "").strip()

        events: list[ToolTraceEvent] = [
            _event(
                tool_id=tool_id,
                event_type="prepare_request",
                title="Prepare web dataset adapter extraction",
                detail=goal[:180],
                data={"url": url, "requested_adapter": requested_adapter},
            )
        ]
        events.append(
            _event(
                tool_id=tool_id,
                event_type="api_call_started",
                title="Select dataset adapter",
                detail=requested_adapter or "LLM adapter selection",
            )
        )
        adapter_name, llm_selected, selection_confidence, selection_reason = self._choose_adapter(
            url=url,
            goal=goal,
            requested_adapter=requested_adapter,
        )
        adapter_config = ADAPTER_SCHEMAS.get(adapter_name) or ADAPTER_SCHEMAS["generic_web_profile"]
        events.append(
            _event(
                tool_id=tool_id,
                event_type="api_call_completed",
                title="Dataset adapter selected",
                detail=adapter_name,
                data={
                    "adapter": adapter_name,
                    "llm_selected": llm_selected,
                    "selection_confidence": selection_confidence,
                    "selection_reason": selection_reason,
                },
            )
        )

        extraction_result = WebStructuredExtractTool().execute(
            context=context,
            prompt=goal,
            params={
                "url": url,
                "page_text": page_text,
                "extraction_goal": str(adapter_config.get("goal") or goal),
                "field_schema": adapter_config.get("schema") or {},
            },
        )
        fallback_used = False
        if llm_selected and adapter_name != "generic_web_profile":
            try:
                quality_score = float(extraction_result.data.get("quality_score") or 0.0)
            except Exception:
                quality_score = 0.0
            try:
                confidence_score = float(extraction_result.data.get("confidence") or 0.0)
            except Exception:
                confidence_score = 0.0
            if max(quality_score, confidence_score) < 0.45:
                fallback_used = True
                events.append(
                    _event(
                        tool_id=tool_id,
                        event_type="tool_progress",
                        title="Fallback to generic adapter",
                        detail=(
                            f"{adapter_name} extraction quality was low "
                            f"(quality={quality_score:.2f}, confidence={confidence_score:.2f})"
                        ),
                        data={
                            "adapter": adapter_name,
                            "quality_score": quality_score,
                            "confidence": confidence_score,
                        },
                    )
                )
                generic_config = ADAPTER_SCHEMAS["generic_web_profile"]
                generic_result = WebStructuredExtractTool().execute(
                    context=context,
                    prompt=goal,
                    params={
                        "url": url,
                        "page_text": page_text,
                        "extraction_goal": str(generic_config.get("goal") or goal),
                        "field_schema": generic_config.get("schema") or {},
                    },
                )
                events.extend(generic_result.events)
                try:
                    generic_quality = float(generic_result.data.get("quality_score") or 0.0)
                except Exception:
                    generic_quality = 0.0
                if generic_quality >= quality_score:
                    extraction_result = generic_result
                    adapter_name = "generic_web_profile"
                    adapter_config = generic_config
        events.extend(extraction_result.events)
        events.append(
            _event(
                tool_id=tool_id,
                event_type="normalize_response",
                title="Normalize adapter output",
                detail=f"Adapter: {adapter_name}",
                data={
                    "adapter": adapter_name,
                    "confidence": extraction_result.data.get("confidence"),
                    "quality_score": extraction_result.data.get("quality_score"),
                    "fallback_used": fallback_used,
                },
            )
        )

        data = dict(extraction_result.data)
        data["adapter"] = adapter_name
        data["adapter_goal"] = str(adapter_config.get("goal") or "")
        data["adapter_schema"] = dict(adapter_config.get("schema") or {})
        data["adapter_selected_by_llm"] = llm_selected
        data["adapter_selection_confidence"] = round(float(selection_confidence), 4)
        data["adapter_selection_reason"] = selection_reason
        data["adapter_fallback_used"] = fallback_used
        return ToolExecutionResult(
            summary=f"Adapter `{adapter_name}` extracted structured web dataset.",
            content=extraction_result.content,
            data=data,
            sources=extraction_result.sources,
            next_steps=extraction_result.next_steps,
            events=events,
        )
