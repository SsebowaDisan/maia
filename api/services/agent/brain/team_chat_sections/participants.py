from __future__ import annotations

from typing import Any


def _humanize_agent_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "Agent"
    return text.replace("_", " ").replace("-", " ").strip().title() or text


def _normalize_agents(agents: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in agents:
        if not isinstance(row, dict):
            continue
        agent_id = str(
            row.get("id") or row.get("agent_id") or row.get("name") or ""
        ).strip()
        if not agent_id:
            continue
        key = agent_id.lower()
        if key in seen:
            continue
        seen.add(key)
        name = str(row.get("name") or "").strip() or _humanize_agent_id(agent_id)
        role = str(row.get("role") or "").strip() or "agent"
        step_description = str(row.get("step_description") or "").strip()
        normalized.append(
            {
                "id": agent_id,
                "agent_id": agent_id,
                "name": name,
                "role": role,
                "step_description": step_description,
            }
        )
    return normalized


def _resolve_participants(
    *,
    requested: Any,
    normalized_agents: list[dict[str, str]],
    limit: int = 4,
) -> list[str]:
    if not normalized_agents:
        return []
    by_id = {
        str(agent["id"]).strip().lower(): str(agent["id"]).strip()
        for agent in normalized_agents
    }
    by_name = {
        str(agent["name"]).strip().lower(): str(agent["id"]).strip()
        for agent in normalized_agents
    }
    resolved: list[str] = []
    values = requested if isinstance(requested, list) else []
    for raw in values:
        token = str(raw or "").strip().lower()
        if not token:
            continue
        candidate = by_id.get(token) or by_name.get(token)
        if not candidate:
            for agent in normalized_agents:
                agent_id = str(agent["id"]).strip()
                agent_name = str(agent["name"]).strip().lower()
                if token in agent_id.lower() or token in agent_name:
                    candidate = agent_id
                    break
        if not candidate or candidate in resolved:
            continue
        resolved.append(candidate)
        if len(resolved) >= limit:
            break
    if resolved:
        return resolved
    return [
        str(agent["id"]).strip()
        for agent in normalized_agents[: min(limit, len(normalized_agents))]
    ]


def _normalized_role(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _resolve_facilitator_agent(
    normalized_agents: list[dict[str, str]],
) -> dict[str, str] | None:
    if not normalized_agents:
        return None
    ranked = sorted(
        normalized_agents,
        key=lambda row: (
            0
            if "supervisor" in _normalized_role(row.get("role", ""))
            else 1
            if _normalized_role(row.get("role", "")) in {"team lead", "lead"}
            else 2
            if "review" in _normalized_role(row.get("role", ""))
            else 3,
            str(row.get("name", "")),
        ),
    )
    best = ranked[0]
    role = _normalized_role(best.get("role", ""))
    if "supervisor" in role or role in {"team lead", "lead"} or "review" in role:
        return best
    return None


def _preferred_watcher_agent(
    candidates: list[dict[str, str]],
    *,
    exclude_id: str = "",
) -> dict[str, str] | None:
    pool = [
        row
        for row in candidates
        if str(row.get("id") or "").strip() != str(exclude_id or "").strip()
    ]
    if not pool:
        return None
    ranked = sorted(
        pool,
        key=lambda row: (
            0
            if "review" in _normalized_role(row.get("role", ""))
            else 1
            if "analyst" in _normalized_role(row.get("role", ""))
            else 2
            if "supervisor" in _normalized_role(row.get("role", ""))
            else 3,
            str(row.get("name", "")),
        ),
    )
    return ranked[0]
