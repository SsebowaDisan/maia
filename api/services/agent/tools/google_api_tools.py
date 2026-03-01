from __future__ import annotations

import json
from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.google_api_catalog import GoogleApiToolSpec, GOOGLE_API_TOOL_SPECS
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)


def _preview_json(payload: Any, *, max_chars: int = 900) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=True, indent=2)
    except Exception:
        text = str(payload)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (truncated)"


def _scene_surface_for_spec(spec: GoogleApiToolSpec) -> str:
    domain = str(spec.domain or "").strip().lower()
    if domain == "email_ops":
        return "email"
    if domain == "document_ops":
        return "document"
    if domain == "marketing_research":
        return "browser"
    return "system"


class GoogleApiCallTool(AgentTool):
    def __init__(self, spec: GoogleApiToolSpec) -> None:
        self.spec = spec
        self.metadata = ToolMetadata(
            tool_id=spec.tool_id,
            action_class=spec.action_class,
            risk_level=spec.risk_level,
            required_permissions=[f"{spec.domain}.api"],
            execution_policy=spec.execution_policy,
            description=spec.description,
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        raw_method = str(params.get("method") or self.spec.default_method).strip().upper()
        if raw_method not in self.spec.allowed_methods:
            allowed = ", ".join(self.spec.allowed_methods)
            raise ToolExecutionError(
                f"Method `{raw_method}` is not allowed for {self.spec.api_name}. Allowed: {allowed}."
            )
        path = str(params.get("path") or self.spec.default_path).strip()
        if not path:
            raise ToolExecutionError(
                f"`path` is required for {self.spec.api_name}."
            )
        query_raw = params.get("query")
        body_raw = params.get("body")
        query = dict(query_raw) if isinstance(query_raw, dict) else {}
        body = dict(body_raw) if isinstance(body_raw, dict) else {}
        scene_surface = _scene_surface_for_spec(self.spec)

        connector = get_connector_registry().build("google_api_hub", settings=context.settings)
        prepared = ToolTraceEvent(
            event_type="tool_progress",
            title=f"Prepare {self.spec.api_name} request",
            detail=f"Auth={self.spec.auth_mode} | Method={raw_method}",
            data={
                "tool_id": self.spec.tool_id,
                "method": raw_method,
                "path": path,
                "scene_surface": scene_surface,
                "flow_id": "standard_api_flow_v1",
            },
        )
        started = ToolTraceEvent(
            event_type="api_call_started",
            title=f"Calling {self.spec.api_name}",
            detail=f"{raw_method} {path}",
            data={
                "tool_id": self.spec.tool_id,
                "method": raw_method,
                "path": path,
                "scene_surface": scene_surface,
                "flow_id": "standard_api_flow_v1",
            },
        )
        payload = connector.call_json_api(
            base_url=self.spec.base_url,
            path=path,
            method=raw_method,
            query=query,
            body=body,
            auth_mode=self.spec.auth_mode,
            api_key_envs=self.spec.api_key_envs,
        )
        payload_dict = payload if isinstance(payload, dict) else {"value": payload}
        top_level_keys = sorted(payload_dict.keys())[:20]
        completed = ToolTraceEvent(
            event_type="api_call_completed",
            title=f"{self.spec.api_name} response received",
            detail=f"Top-level keys: {', '.join(top_level_keys) if top_level_keys else 'none'}",
            data={
                "tool_id": self.spec.tool_id,
                "top_level_keys": top_level_keys,
                "scene_surface": scene_surface,
                "flow_id": "standard_api_flow_v1",
            },
        )
        normalized = ToolTraceEvent(
            event_type="tool_progress",
            title="Normalize API response for downstream steps",
            detail=f"Prepared structured preview with {len(top_level_keys)} top-level key(s)",
            data={
                "tool_id": self.spec.tool_id,
                "top_level_keys": top_level_keys,
                "scene_surface": scene_surface,
                "flow_id": "standard_api_flow_v1",
            },
        )
        content = "\n".join(
            [
                f"### {self.spec.api_name}",
                f"- Tool ID: `{self.spec.tool_id}`",
                f"- Method: `{raw_method}`",
                f"- Path: `{path}`",
                f"- Top-level keys: {', '.join(top_level_keys) if top_level_keys else 'none'}",
                "",
                "### Response preview",
                "```json",
                _preview_json(payload_dict),
                "```",
            ]
        )
        return ToolExecutionResult(
            summary=f"{self.spec.api_name} call completed.",
            content=content,
            data={
                "api_name": self.spec.api_name,
                "tool_id": self.spec.tool_id,
                "method": raw_method,
                "path": path,
                "query": query,
                "response": payload_dict,
                "scene_surface": scene_surface,
                "flow_id": "standard_api_flow_v1",
            },
            sources=[],
            next_steps=[
                "Use parsed response fields for downstream business decisions.",
                "Log selected evidence rows to Google Docs/Sheets in theatre mode.",
            ],
            events=[prepared, started, completed, normalized],
        )


def build_google_api_tools() -> list[AgentTool]:
    return [GoogleApiCallTool(spec) for spec in GOOGLE_API_TOOL_SPECS]
