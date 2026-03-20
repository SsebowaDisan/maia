from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from api.services.agent.connectors.plugin_manifest import connector_plugin_action_hints

EVENT_ENVELOPE_VERSION = "event_envelope_v2"

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
EventPriority = Literal["critical", "important", "contextual", "background", "internal"]
EventRenderMode = Literal["animate_live", "summarize", "compress", "replay_later"]
EventReplayImportance = Literal["critical", "high", "normal", "low", "internal"]

_ROLE_LABELS: dict[str, str] = {
    "conductor": "Conductor",
    "planner": "Planner",
    "research": "Research",
    "browser": "Browser",
    "writer": "Writer",
    "verifier": "Verifier",
    "safety": "Safety",
    "document_reader": "Document",
    "analyst": "Analyst",
    "chart_builder": "Analyst",
    "workspace_editor": "Writer",
    "goal_page_discovery": "Browser",
    "contact_form": "Browser",
    "system": "System",
}

_ROLE_COLORS: dict[str, str] = {
    "conductor": "#2563eb",
    "planner": "#7c3aed",
    "research": "#0ea5e9",
    "browser": "#0284c7",
    "writer": "#7c2d12",
    "verifier": "#15803d",
    "safety": "#dc2626",
    "document_reader": "#475569",
    "analyst": "#1d4ed8",
    "chart_builder": "#1d4ed8",
    "workspace_editor": "#9333ea",
    "goal_page_discovery": "#0369a1",
    "contact_form": "#0369a1",
    "system": "#6b7280",
}


class EventEnvelope(BaseModel):
    envelope_version: str = EVENT_ENVELOPE_VERSION
    event_family: EventFamily
    event_type: str
    stage: str = "system"
    status: str = "info"
    priority: EventPriority
    render_mode: EventRenderMode
    replay_importance: EventReplayImportance
    agent_id: str | None = None
    agent_role: str | None = None
    agent_label: str | None = None
    agent_color: str | None = None
    graph_node_id: str | None = None
    scene_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    # Theatre correlation fields
    scene_family: str | None = None
    connector_id: str | None = None
    connector_label: str | None = None
    brand_slug: str | None = None
    operation_label: str | None = None
    computer_use_session_id: str | None = None


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_text(value: Any) -> str:
    return _clean_text(value).lower()


def _first_text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        if key not in data:
            continue
        text = _clean_text(data.get(key))
        if text:
            return text
    return None


def _collect_refs(data: dict[str, Any], *keys: str) -> list[str]:
    refs: list[str] = []
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            refs.extend([_clean_text(item) for item in value if _clean_text(item)])
            continue
        text = _clean_text(value)
        if text:
            refs.append(text)
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(refs))


def _tokenized(value: Any) -> str:
    return _normalized_text(value).replace("-", "_").replace(" ", "_")


def _title_from_token(token: str) -> str:
    return " ".join(
        part[:1].upper() + part[1:]
        for part in str(token or "").split("_")
        if part
    )


def _agent_profile(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    role = _tokenized(
        _first_text(payload, "agent_role", "owner_role", "__owner_role", "role", "to_role")
    )
    agent_id = _first_text(payload, "agent_id")
    if not agent_id and role:
        agent_id = f"agent.{role}"
    label = _first_text(payload, "agent_label")
    if not label and role:
        label = _ROLE_LABELS.get(role) or _title_from_token(role)
    color = _first_text(payload, "agent_color")
    if not color and role:
        color = _ROLE_COLORS.get(role) or _ROLE_COLORS["system"]
    return agent_id, role or None, label, color


_FAMILY_EXACT: dict[str, EventFamily] = {
    "agent.handoff": "plan",
    "agent.resume": "plan",
    "agent.waiting": "approval",
    "agent.blocked": "approval",
    "approval_required": "approval",
    "approval_granted": "approval",
    "policy_blocked": "approval",
    "handoff_paused": "approval",
    "handoff_resumed": "approval",
    "event_coverage": "verify",
    "web_kpi_summary": "verify",
    "web_evidence_summary": "verify",
    "web_release_gate": "verify",
    # Brain review events
    "brain_review_started": "plan",
    "brain_review_decision": "plan",
    "brain_revision_requested": "plan",
    "brain_question": "plan",
    "brain_answer_received": "plan",
    "brain_review_summary": "plan",
    # Agent dialogue events
    "agent_dialogue_turn": "plan",
    "agent_dialogue_started": "plan",
    "agent_dialogue_resolved": "plan",
    # Assembly events
    "assembly_brain_thinking": "plan",
    "assembly_step_added": "plan",
    "assembly_edge_added": "plan",
    "assembly_narration": "plan",
    "assembly_connector_needed": "plan",
    "assembly_schedule_detected": "plan",
    "assembly_complete": "plan",
}

_CRITICAL_EVENTS: set[str] = {
    "agent.blocked",
    "agent.waiting",
    "approval_required",
    "policy_blocked",
    "handoff_paused",
    "browser_human_verification_required",
    "browser_contact_human_verification_required",
}

_AGENT_EVENT_ALIASES: dict[str, str] = {
    "role_handoff": "agent.handoff",
    "role_activated": "agent.resume",
    "handoff_paused": "agent.waiting",
    "approval_required": "agent.waiting",
    "handoff_resumed": "agent.resume",
    "policy_blocked": "agent.blocked",
}


def _workspace_render_mode(value: Any) -> str:
    normalized = _normalized_text(value)
    if normalized in {"fast", "balanced", "full", "full_theatre"}:
        return "full_theatre" if normalized == "full" else normalized
    return ""


def infer_event_family(
    *,
    event_type: str,
    stage: str = "system",
    data: dict[str, Any] | None = None,
) -> EventFamily:
    normalized = _normalized_text(event_type)

    # Priority 1: Check declared scene_family from event data (metadata-driven, no heuristics)
    declared_scene_family = _normalized_text((data or {}).get("scene_family"))
    _SCENE_FAMILY_TO_EVENT_FAMILY: dict[str, EventFamily] = {
        "email": "email", "sheet": "sheet", "document": "doc", "api": "api",
        "browser": "browser", "chat": "api", "crm": "api", "support": "api", "commerce": "api",
    }
    if declared_scene_family in _SCENE_FAMILY_TO_EVENT_FAMILY:
        return _SCENE_FAMILY_TO_EVENT_FAMILY[declared_scene_family]

    if normalized in _FAMILY_EXACT:
        return _FAMILY_EXACT[normalized]
    if normalized.startswith("graph_"):
        return "graph"
    if normalized.startswith("scene_"):
        return "scene"
    if normalized.startswith(("browser_", "browser.", "web_", "web.", "brave.", "bing.")):
        return "browser"
    if normalized.startswith(("pdf_", "pdf.")):
        return "pdf"
    if normalized.startswith(("doc_", "doc.", "docs.", "document_")):
        return "doc"
    if normalized.startswith(("sheet_", "sheet.", "sheets.")):
        return "sheet"
    if normalized.startswith(("email_", "email.", "gmail_", "gmail.", "outlook_", "outlook.")):
        return "email"
    if normalized.startswith(("api_", "api.", "api_call_", "sap_", "sap.", "connector_", "connector.")):
        return "api"
    if normalized.startswith(("computer_use_",)):
        return "browser"
    if normalized.startswith(("slack_", "slack.", "teams_", "teams.")):
        return "api"
    if normalized.startswith(("memory_", "llm.context_memory", "llm.context_session", "llm.working_context")):
        return "memory"
    if normalized.startswith(("artifact_", "report.", "workspace.")):
        return "artifact"
    if normalized.startswith(("verification_", "llm.delivery_check", "retrieval_quality_assessed")):
        return "verify"
    if normalized.startswith(("planning_", "plan_", "task_understanding", "role_", "retrieval_query_rewrite")):
        return "plan"
    if normalized.startswith("llm."):
        if ".delivery_check" in normalized or ".verification" in normalized:
            return "verify"
        if ".context_" in normalized or ".working_context" in normalized:
            return "memory"
        return "plan"

    normalized_stage = _normalized_text(stage)
    if normalized_stage == "plan":
        return "plan"
    if normalized_stage in {"preview", "ui_action"}:
        return "scene"
    if normalized_stage in {"result", "error"}:
        return "verify"

    declared_family = _normalized_text((data or {}).get("event_family"))
    if declared_family in {
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
    }:
        return declared_family  # type: ignore[return-value]
    return "system"


def infer_event_priority(
    *,
    event_type: str,
    status: str,
    stage: str,
    event_family: EventFamily,
) -> EventPriority:
    normalized_event = _normalized_text(event_type)
    normalized_status = _normalized_text(status)
    normalized_stage = _normalized_text(stage)

    if normalized_event in _CRITICAL_EVENTS:
        return "critical"
    if normalized_status in {"failed", "blocked"} or normalized_stage == "error":
        return "important"
    if normalized_status == "waiting" and event_family in {"approval", "verify"}:
        return "important"
    if normalized_event.endswith("_progress"):
        return "background"
    if normalized_status == "in_progress":
        return "contextual"
    if normalized_event.endswith(("_started", "_completed", "_ready")):
        return "contextual"
    if event_family in {"plan", "browser", "pdf", "doc", "sheet", "email", "verify", "approval", "api"}:
        return "contextual"
    return "internal"


def infer_render_mode(
    *,
    event_family: EventFamily,
    priority: EventPriority,
) -> EventRenderMode:
    if priority in {"critical", "important"}:
        return "animate_live"
    if priority == "background":
        return "compress"
    if priority == "internal":
        return "replay_later"
    if event_family in {"browser", "pdf", "doc", "sheet", "email", "scene", "plan"}:
        return "animate_live"
    return "summarize"


def infer_replay_importance(*, priority: EventPriority) -> EventReplayImportance:
    if priority == "critical":
        return "critical"
    if priority == "important":
        return "high"
    if priority == "contextual":
        return "normal"
    if priority == "background":
        return "low"
    return "internal"


def apply_workspace_mode_policy(
    *,
    payload: dict[str, Any],
    priority: EventPriority,
    default_render_mode: EventRenderMode,
    default_replay_importance: EventReplayImportance,
) -> tuple[EventRenderMode, EventReplayImportance]:
    workspace_mode = _workspace_render_mode(
        payload.get("__workspace_render_mode") or payload.get("workspace_render_mode")
    )
    if workspace_mode == "fast":
        if priority in {"critical", "important", "internal"}:
            return default_render_mode, default_replay_importance
        return "compress", "low"
    if workspace_mode == "full_theatre":
        if priority == "internal":
            return default_render_mode, default_replay_importance
        if priority in {"critical", "important"}:
            return "animate_live", default_replay_importance
        if priority == "background":
            return "animate_live", "normal"
        return "animate_live", "high"
    return default_render_mode, default_replay_importance


def build_event_envelope(
    *,
    event_type: str,
    stage: str,
    status: str,
    data: dict[str, Any] | None = None,
) -> EventEnvelope:
    payload = dict(data or {})
    agent_id, agent_role, agent_label, agent_color = _agent_profile(payload)
    family = infer_event_family(event_type=event_type, stage=stage, data=payload)
    priority = infer_event_priority(
        event_type=event_type,
        status=status,
        stage=stage,
        event_family=family,
    )
    render_mode, replay_importance = apply_workspace_mode_policy(
        payload=payload,
        priority=priority,
        default_render_mode=infer_render_mode(event_family=family, priority=priority),
        default_replay_importance=infer_replay_importance(priority=priority),
    )
    # Theatre correlation
    connector_id = _first_text(payload, "connector_id", "provider", "integration_id")
    connector_label = _first_text(payload, "connector_label", "provider_label")
    brand_slug = _first_text(payload, "brand_slug", "plugin_brand_slug")
    scene_family = _first_text(payload, "scene_family", "plugin_scene_family")
    operation_label = _first_text(payload, "operation_label", "action_label", "operation")
    cu_session_id = _first_text(payload, "computer_use_session_id")

    # Enrich from plugin metadata if connector is known
    if connector_id and not scene_family:
        try:
            hints = connector_plugin_action_hints(connector_id=connector_id)
            scene_family = scene_family or hints.get("plugin_scene_family")
            brand_slug = brand_slug or hints.get("plugin_brand_slug")
            connector_label = connector_label or hints.get("plugin_connector_label")
        except Exception:
            pass

    return EventEnvelope(
        event_family=family,
        event_type=_clean_text(event_type) or "unknown",
        stage=_clean_text(stage) or "system",
        status=_clean_text(status) or "info",
        priority=priority,
        render_mode=render_mode,
        replay_importance=replay_importance,
        agent_id=agent_id,
        agent_role=agent_role,
        agent_label=agent_label,
        agent_color=agent_color,
        graph_node_id=_first_text(payload, "graph_node_id"),
        scene_ref=_first_text(payload, "scene_ref", "scene_surface"),
        evidence_refs=_collect_refs(payload, "evidence_refs", "evidence_ids"),
        artifact_refs=_collect_refs(payload, "artifact_refs", "artifact_ids"),
        scene_family=scene_family,
        connector_id=connector_id,
        connector_label=connector_label,
        brand_slug=brand_slug,
        operation_label=operation_label,
        computer_use_session_id=cu_session_id,
    )


def merge_event_envelope_data(
    *,
    data: dict[str, Any] | None,
    envelope: EventEnvelope,
    event_schema_version: str,
) -> dict[str, Any]:
    merged = dict(data or {})
    merged["event_schema_version"] = _clean_text(event_schema_version) or "1.0"
    merged["event_family"] = envelope.event_family
    merged["event_priority"] = envelope.priority
    merged["event_render_mode"] = envelope.render_mode
    merged["event_replay_importance"] = envelope.replay_importance
    merged["event_envelope_version"] = envelope.envelope_version
    alias = _AGENT_EVENT_ALIASES.get(_normalized_text(envelope.event_type))
    if alias:
        merged.setdefault("agent_event_type", alias)
    if envelope.agent_id and not _clean_text(merged.get("agent_id")):
        merged["agent_id"] = envelope.agent_id
    if envelope.agent_role and not _clean_text(merged.get("agent_role")):
        merged["agent_role"] = envelope.agent_role
    if envelope.agent_label and not _clean_text(merged.get("agent_label")):
        merged["agent_label"] = envelope.agent_label
    if envelope.agent_color and not _clean_text(merged.get("agent_color")):
        merged["agent_color"] = envelope.agent_color
    if envelope.graph_node_id and not _clean_text(merged.get("graph_node_id")):
        merged["graph_node_id"] = envelope.graph_node_id
    if envelope.graph_node_id and not merged.get("graph_node_ids"):
        merged["graph_node_ids"] = [envelope.graph_node_id]
    if envelope.scene_ref and not _clean_text(merged.get("scene_ref")):
        merged["scene_ref"] = envelope.scene_ref
    if envelope.scene_ref and not merged.get("scene_refs"):
        merged["scene_refs"] = [envelope.scene_ref]
    if envelope.event_family == "api":
        connector_id = _first_text(merged, "connector_id", "provider", "integration_id")
        action_id = _first_text(merged, "action_id", "plugin_action_id", "operation_id")
        if connector_id:
            try:
                plugin_hints = connector_plugin_action_hints(connector_id=connector_id, action_id=action_id)
            except Exception:
                plugin_hints = {}
            for key, value in plugin_hints.items():
                if _clean_text(value) and not _clean_text(merged.get(key)):
                    merged[key] = value
            if not _clean_text(merged.get("scene_surface")) and _clean_text(plugin_hints.get("plugin_scene_type")):
                merged["scene_surface"] = plugin_hints["plugin_scene_type"]
            if not _clean_text(merged.get("scene_ref")) and _clean_text(plugin_hints.get("plugin_scene_type")):
                merged["scene_ref"] = plugin_hints["plugin_scene_type"]

    # Propagate theatre correlation fields from envelope to event data
    if envelope.scene_family and not _clean_text(merged.get("scene_family")):
        merged["scene_family"] = envelope.scene_family
    if envelope.connector_id and not _clean_text(merged.get("connector_id")):
        merged["connector_id"] = envelope.connector_id
    if envelope.connector_label and not _clean_text(merged.get("connector_label")):
        merged["connector_label"] = envelope.connector_label
    if envelope.brand_slug and not _clean_text(merged.get("brand_slug")):
        merged["brand_slug"] = envelope.brand_slug
    if envelope.operation_label and not _clean_text(merged.get("operation_label")):
        merged["operation_label"] = envelope.operation_label
    if envelope.computer_use_session_id and not _clean_text(merged.get("computer_use_session_id")):
        merged["computer_use_session_id"] = envelope.computer_use_session_id

    merged["event_envelope"] = envelope.model_dump(mode="json")
    return merged


__all__ = [
    "EVENT_ENVELOPE_VERSION",
    "EventEnvelope",
    "EventFamily",
    "EventPriority",
    "EventReplayImportance",
    "EventRenderMode",
    "build_event_envelope",
    "apply_workspace_mode_policy",
    "infer_event_family",
    "infer_event_priority",
    "infer_render_mode",
    "infer_replay_importance",
    "merge_event_envelope_data",
]
