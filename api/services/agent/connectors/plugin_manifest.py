from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


SceneType = Literal["system", "browser", "document", "email", "sheet", "api"]
EventFamily = Literal[
    "plan",
    "graph",
    "scene",
    "browser",
    "pdf",
    "doc",
    "sheet",
    "email",
    "api",
    "verify",
    "approval",
    "memory",
    "artifact",
    "system",
]
EvidenceSourceType = Literal["web", "pdf", "sheet", "email", "api", "document"]
WorkGraphNodeType = Literal[
    "task",
    "plan_step",
    "research",
    "browser_action",
    "document_review",
    "spreadsheet_analysis",
    "email_draft",
    "verification",
    "approval",
    "artifact",
    "memory_lookup",
    "api_operation",
    "decision",
]
GraphEdgeFamily = Literal["sequential", "dependency", "evidence", "verification"]


class PluginActionManifest(BaseModel):
    action_id: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9_]+(?:[.-][a-z0-9_]+)+$")
    title: str = Field(min_length=2, max_length=120)
    description: str = ""
    event_family: EventFamily = "api"
    scene_type: SceneType = "system"
    tool_ids: list[str] = Field(default_factory=list, max_length=20)


class PluginEvidenceEmitter(BaseModel):
    emitter_id: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9_]+(?:[.-][a-z0-9_]+)+$")
    source_type: EvidenceSourceType
    fields: list[str] = Field(default_factory=list, max_length=25)


class PluginSceneMapping(BaseModel):
    scene_type: SceneType
    action_ids: list[str] = Field(default_factory=list, max_length=40)


class PluginGraphMapping(BaseModel):
    action_id: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9_]+(?:[.-][a-z0-9_]+)+$")
    node_type: WorkGraphNodeType
    edge_family: GraphEdgeFamily = "sequential"


class ConnectorPluginManifest(BaseModel):
    connector_id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=2, max_length=120)
    enabled: bool = True
    actions: list[PluginActionManifest] = Field(default_factory=list)
    evidence_emitters: list[PluginEvidenceEmitter] = Field(default_factory=list)
    scene_mapping: list[PluginSceneMapping] = Field(default_factory=list)
    graph_mapping: list[PluginGraphMapping] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_mapping_integrity(self) -> "ConnectorPluginManifest":
        action_ids = [row.action_id for row in self.actions]
        known_action_ids = set(action_ids)
        if len(known_action_ids) != len(action_ids):
            raise ValueError("actions must not contain duplicate action_id values.")

        emitter_ids = [row.emitter_id for row in self.evidence_emitters]
        known_emitter_ids = set(emitter_ids)
        if len(known_emitter_ids) != len(emitter_ids):
            raise ValueError("evidence_emitters must not contain duplicate emitter_id values.")

        scene_action_ids = {
            action_id
            for scene_mapping in self.scene_mapping
            for action_id in scene_mapping.action_ids
            if str(action_id).strip()
        }
        unknown_scene_refs = sorted(scene_action_ids - known_action_ids)
        if unknown_scene_refs:
            raise ValueError(
                f"scene_mapping references unknown action_ids: {', '.join(unknown_scene_refs)}"
            )

        graph_action_ids = {
            graph_mapping.action_id
            for graph_mapping in self.graph_mapping
            if str(graph_mapping.action_id).strip()
        }
        unknown_graph_refs = sorted(graph_action_ids - known_action_ids)
        if unknown_graph_refs:
            raise ValueError(
                f"graph_mapping references unknown action_ids: {', '.join(unknown_graph_refs)}"
            )
        return self


def _title_case(value: str) -> str:
    parts = [part for part in str(value or "").replace("-", "_").split("_") if part]
    return " ".join(part[:1].upper() + part[1:] for part in parts) or "Connector"


def _profile_for_connector(connector_id: str) -> dict[str, object]:
    normalized = str(connector_id or "").strip().lower()
    profiles: dict[str, dict[str, object]] = {
        "gmail": {
            "label": "Gmail",
            "actions": [
                {"action_id": "email.send", "title": "Send email", "event_family": "email", "scene_type": "email"},
                {"action_id": "email.search", "title": "Search inbox", "event_family": "email", "scene_type": "email"},
            ],
            "evidence_emitters": [
                {"emitter_id": "gmail.thread", "source_type": "email", "fields": ["thread_id", "subject", "snippet"]},
            ],
            "scene_mapping": [{"scene_type": "email", "action_ids": ["email.send", "email.search"]}],
            "graph_mapping": [
                {"action_id": "email.send", "node_type": "email_draft"},
                {"action_id": "email.search", "node_type": "research"},
            ],
        },
        "google_analytics": {
            "label": "Google Analytics",
            "actions": [
                {
                    "action_id": "analytics.fetch_report",
                    "title": "Fetch report",
                    "event_family": "api",
                    "scene_type": "api",
                },
            ],
            "evidence_emitters": [
                {
                    "emitter_id": "ga.report",
                    "source_type": "api",
                    "fields": ["property_id", "report_range", "metrics"],
                },
            ],
            "scene_mapping": [{"scene_type": "api", "action_ids": ["analytics.fetch_report"]}],
            "graph_mapping": [{"action_id": "analytics.fetch_report", "node_type": "api_operation"}],
        },
        "playwright_browser": {
            "label": "Playwright Browser",
            "actions": [
                {"action_id": "browser.navigate", "title": "Navigate", "event_family": "browser", "scene_type": "browser"},
                {"action_id": "browser.extract", "title": "Extract", "event_family": "browser", "scene_type": "browser"},
            ],
            "evidence_emitters": [
                {"emitter_id": "browser.capture", "source_type": "web", "fields": ["url", "snippet", "event_id"]},
            ],
            "scene_mapping": [{"scene_type": "browser", "action_ids": ["browser.navigate", "browser.extract"]}],
            "graph_mapping": [
                {"action_id": "browser.navigate", "node_type": "browser_action"},
                {"action_id": "browser.extract", "node_type": "research"},
            ],
        },
    }
    profile = profiles.get(normalized)
    if profile:
        return profile
    return {
        "label": _title_case(normalized or "connector"),
        "actions": [
            {
                "action_id": f"{normalized or 'connector'}.call",
                "title": "Execute connector action",
                "event_family": "api",
                "scene_type": "api",
            }
        ],
        "evidence_emitters": [
            {
                "emitter_id": f"{normalized or 'connector'}.evidence",
                "source_type": "api",
                "fields": ["event_id", "result"],
            }
        ],
        "scene_mapping": [{"scene_type": "api", "action_ids": [f"{normalized or 'connector'}.call"]}],
        "graph_mapping": [{"action_id": f"{normalized or 'connector'}.call", "node_type": "api_operation"}],
    }


def connector_plugin_manifest(*, connector_id: str, enabled: bool = True) -> ConnectorPluginManifest:
    profile = _profile_for_connector(connector_id)
    return ConnectorPluginManifest(
        connector_id=str(connector_id or "").strip() or "unknown",
        label=str(profile.get("label") or _title_case(connector_id)),
        enabled=bool(enabled),
        actions=[PluginActionManifest.model_validate(row) for row in list(profile.get("actions") or [])],
        evidence_emitters=[
            PluginEvidenceEmitter.model_validate(row) for row in list(profile.get("evidence_emitters") or [])
        ],
        scene_mapping=[PluginSceneMapping.model_validate(row) for row in list(profile.get("scene_mapping") or [])],
        graph_mapping=[PluginGraphMapping.model_validate(row) for row in list(profile.get("graph_mapping") or [])],
    )


def connector_plugin_action_hints(
    *,
    connector_id: str,
    action_id: str | None = None,
) -> dict[str, str]:
    manifest = connector_plugin_manifest(connector_id=connector_id, enabled=True)
    normalized_action_id = str(action_id or "").strip().lower()
    selected_action = None
    if normalized_action_id:
        selected_action = next(
            (row for row in manifest.actions if row.action_id.lower() == normalized_action_id),
            None,
        )

    selected_scene = None
    if selected_action:
        selected_scene = selected_action.scene_type
    elif normalized_action_id:
        scene_mapping = next(
            (
                row
                for row in manifest.scene_mapping
                if any(item.lower() == normalized_action_id for item in row.action_ids)
            ),
            None,
        )
        if scene_mapping:
            selected_scene = scene_mapping.scene_type
    elif manifest.scene_mapping:
        selected_scene = manifest.scene_mapping[0].scene_type
    elif manifest.actions:
        selected_scene = manifest.actions[0].scene_type

    selected_graph = None
    if normalized_action_id:
        selected_graph = next(
            (row for row in manifest.graph_mapping if row.action_id.lower() == normalized_action_id),
            None,
        )
    elif manifest.graph_mapping:
        selected_graph = manifest.graph_mapping[0]

    hints: dict[str, str] = {
        "plugin_connector_id": manifest.connector_id,
        "plugin_connector_label": manifest.label,
    }
    if selected_action:
        hints["plugin_action_id"] = selected_action.action_id
        hints["plugin_action_title"] = selected_action.title
        hints["plugin_action_family"] = selected_action.event_family
    if selected_scene:
        hints["plugin_scene_type"] = selected_scene
    if selected_graph:
        hints["plugin_graph_node_type"] = selected_graph.node_type
        hints["plugin_graph_edge_family"] = selected_graph.edge_family
    return hints


__all__ = [
    "ConnectorPluginManifest",
    "PluginActionManifest",
    "PluginEvidenceEmitter",
    "PluginGraphMapping",
    "PluginSceneMapping",
    "connector_plugin_action_hints",
    "connector_plugin_manifest",
]
