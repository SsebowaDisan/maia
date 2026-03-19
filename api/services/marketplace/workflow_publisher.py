"""Workflow publishing and installation for marketplace teams."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any

from sqlmodel import Session, SQLModel, select

from api.models.creator_profile import CreatorProfile
from api.models.published_workflow import PublishedWorkflow
from api.models.workflow import WorkflowRecord
from api.services.marketplace.abuse_prevention import consume_daily_quota
from api.services.marketplace.feed import record_feed_event
from ktem.db.engine import engine

logger = logging.getLogger(__name__)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def _slugify(text: str) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    raw = raw[:56]
    if len(raw) < 3:
        return "team"
    return raw


def _generate_slug(name: str) -> str:
    base = _slugify(name)
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _ensure_unique_slug(session: Session, preferred: str) -> str:
    candidate = preferred
    for _ in range(20):
        exists = session.exec(
            select(PublishedWorkflow).where(PublishedWorkflow.slug == candidate)
        ).first()
        if not exists:
            return candidate
        candidate = f"{_slugify(preferred)}-{uuid.uuid4().hex[:6]}"
    return f"team-{uuid.uuid4().hex[:10]}"


def _extract_agent_lineup(definition: dict[str, Any]) -> list[dict[str, Any]]:
    steps = definition.get("steps", [])
    lineup: list[dict[str, Any]] = []
    seen_agents: set[str] = set()
    for step in steps:
        agent_id = str(step.get("agent_id", "")).strip()
        if not agent_id or agent_id in seen_agents:
            continue
        seen_agents.add(agent_id)
        lineup.append(
            {
                "agent_id": agent_id,
                "step_id": str(step.get("step_id", "")).strip(),
                "description": str(step.get("description", "")).strip(),
                "step_type": str(step.get("step_type", "agent")).strip() or "agent",
            }
        )
    return lineup


def _extract_required_connectors(creator_id: str, lineup: list[dict[str, Any]]) -> list[str]:
    required: list[str] = []
    try:
        from api.services.agents.definition_store import get_agent
    except Exception:
        return required
    for agent_info in lineup:
        agent_id = str(agent_info.get("agent_id", "")).strip()
        if not agent_id:
            continue
        try:
            agent_record = get_agent(creator_id, agent_id)
            definition = (agent_record.definition or {}) if agent_record else {}
            connectors = definition.get("required_connectors") or []
            for connector_id in connectors:
                cid = str(connector_id or "").strip()
                if cid and cid not in required:
                    required.append(cid)
        except Exception:
            continue
    return required


def _ensure_creator_profile(session: Session, creator_id: str) -> CreatorProfile:
    profile = session.exec(
        select(CreatorProfile).where(CreatorProfile.user_id == creator_id)
    ).first()
    if profile:
        return profile
    username_seed = re.sub(r"[^a-z0-9]+", "-", creator_id.lower()).strip("-")[:24] or "creator"
    username = f"{username_seed}-{uuid.uuid4().hex[:4]}"
    profile = CreatorProfile(
        user_id=creator_id,
        username=username,
        display_name=f"Creator {creator_id[:8]}",
    )
    session.add(profile)
    session.flush()
    return profile


def publish_workflow(
    *,
    creator_id: str,
    source_workflow_id: str,
    name: str,
    description: str = "",
    readme_md: str = "",
    definition: dict[str, Any],
    category: str = "other",
    tags: list[str] | None = None,
    screenshots: list[str] | None = None,
) -> dict[str, Any]:
    """Create or update a published marketplace workflow."""
    _ensure_tables()

    clean_name = str(name or "").strip() or "Untitled team"
    clean_description = str(description or "").strip()
    clean_readme = str(readme_md or "").strip()
    clean_tags = [str(tag).strip() for tag in (tags or []) if str(tag).strip()]
    clean_shots = [str(url).strip() for url in (screenshots or []) if str(url).strip()]
    lineup = _extract_agent_lineup(definition)
    required_connectors = _extract_required_connectors(creator_id, lineup)

    with Session(engine) as session:
        profile = _ensure_creator_profile(session, creator_id)
        existing = session.exec(
            select(PublishedWorkflow).where(
                PublishedWorkflow.creator_id == creator_id,
                PublishedWorkflow.source_workflow_id == source_workflow_id,
            )
        ).first()

        created_new = existing is None
        if existing:
            existing.name = clean_name
            existing.description = clean_description
            existing.readme_md = clean_readme
            existing.definition_snapshot = definition
            existing.agent_lineup = lineup
            existing.required_connectors = required_connectors
            existing.category = str(category or "other").strip()[:40] or "other"
            existing.tags = clean_tags
            existing.screenshots = clean_shots
            existing.date_updated = datetime.utcnow()
            session.add(existing)
            row = existing
        else:
            consume_daily_quota(
                user_id=creator_id,
                action_key="marketplace_team_publish",
                daily_limit=10,
            )
            slug = _ensure_unique_slug(session, _generate_slug(clean_name))
            row = PublishedWorkflow(
                slug=slug,
                creator_id=creator_id,
                source_workflow_id=source_workflow_id,
                name=clean_name,
                description=clean_description,
                readme_md=clean_readme,
                definition_snapshot=definition,
                agent_lineup=lineup,
                required_connectors=required_connectors,
                category=str(category or "other").strip()[:40] or "other",
                tags=clean_tags,
                screenshots=clean_shots,
            )
            session.add(row)
            profile.published_team_count = int(profile.published_team_count or 0) + 1
            session.add(profile)

        session.commit()
        session.refresh(row)
        session.refresh(profile)

    try:
        record_feed_event(
            creator_user_id=creator_id,
            actor_user_id=creator_id,
            event_type="team_published" if created_new else "team_updated",
            entity_type="team",
            entity_id=row.id,
            slug=row.slug,
            title=row.name,
            summary=row.description or row.readme_md[:260],
            payload={
                "category": row.category,
                "tags": row.tags or [],
                "required_connectors": row.required_connectors or [],
                "version": row.version,
            },
        )
    except Exception:
        logger.debug("record_feed_event failed for published workflow", exc_info=True)

    return _to_dict(row, include_definition=True)


def get_published_workflow(slug: str) -> dict[str, Any] | None:
    _ensure_tables()
    with Session(engine) as session:
        row = session.exec(
            select(PublishedWorkflow).where(PublishedWorkflow.slug == slug)
        ).first()
        if not row:
            return None
        profile = session.exec(
            select(CreatorProfile).where(CreatorProfile.user_id == row.creator_id)
        ).first()
        return _to_dict(row, include_definition=True, profile=profile)


def list_published_workflows(
    *,
    creator_id: str | None = None,
    category: str | None = None,
    q: str | None = None,
    sort: str = "popular",
    limit: int = 50,
) -> list[dict[str, Any]]:
    _ensure_tables()
    with Session(engine) as session:
        stmt = select(PublishedWorkflow).where(PublishedWorkflow.status == "published")
        if creator_id:
            stmt = stmt.where(PublishedWorkflow.creator_id == creator_id)
        if category:
            stmt = stmt.where(PublishedWorkflow.category == category)
        query = str(q or "").strip().lower()
        rows = session.exec(stmt).all()
        if query:
            rows = [
                row
                for row in rows
                if query in row.name.lower()
                or query in row.description.lower()
                or any(query in str(tag).lower() for tag in (row.tags or []))
            ]
        if sort == "newest":
            rows.sort(key=lambda row: row.date_created or datetime.min, reverse=True)
        elif sort == "trending":
            rows.sort(
                key=lambda row: ((row.install_count or 0) * 2) + (row.avg_rating or 0.0),
                reverse=True,
            )
        else:
            rows.sort(
                key=lambda row: ((row.install_count or 0), row.avg_rating or 0.0),
                reverse=True,
            )
        rows = rows[: min(max(limit, 1), 100)]
        creator_ids = {row.creator_id for row in rows}
        profiles = {
            profile.user_id: profile
            for profile in session.exec(
                select(CreatorProfile).where(CreatorProfile.user_id.in_(creator_ids))
            ).all()
        }
        return [_to_dict(row, include_definition=False, profile=profiles.get(row.creator_id)) for row in rows]


def list_related_workflows(slug: str, *, limit: int = 6) -> list[dict[str, Any]]:
    _ensure_tables()
    with Session(engine) as session:
        base = session.exec(
            select(PublishedWorkflow).where(PublishedWorkflow.slug == slug)
        ).first()
        if not base:
            return []
        rows = session.exec(
            select(PublishedWorkflow)
            .where(PublishedWorkflow.status == "published")
            .where(PublishedWorkflow.slug != slug)
            .limit(120)
        ).all()
        scored: list[tuple[float, PublishedWorkflow]] = []
        base_tags = set(base.tags or [])
        for row in rows:
            score = 0.0
            if row.category == base.category:
                score += 2.0
            overlap = len(base_tags.intersection(set(row.tags or [])))
            score += overlap * 0.8
            score += min((row.install_count or 0) / 500.0, 1.2)
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top_rows = [row for _, row in scored[: min(max(limit, 1), 20)]]
        creator_ids = {row.creator_id for row in top_rows}
        profiles = {
            profile.user_id: profile
            for profile in session.exec(
                select(CreatorProfile).where(CreatorProfile.user_id.in_(creator_ids))
            ).all()
        }
        return [_to_dict(row, include_definition=False, profile=profiles.get(row.creator_id)) for row in top_rows]


def install_workflow(
    *,
    slug: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Install or reuse a published workflow in the target tenant."""
    _ensure_tables()
    with Session(engine) as session:
        row = session.exec(
            select(PublishedWorkflow).where(PublishedWorkflow.slug == slug)
        ).first()
        if not row:
            raise ValueError(f"Published workflow '{slug}' not found.")

        # Idempotency: if installed before by this tenant, reuse the existing workflow.
        existing = session.exec(
            select(WorkflowRecord)
            .where(WorkflowRecord.tenant_id == tenant_id)
            .where(WorkflowRecord.is_active == True)  # noqa: E712
        ).all()
        existing_record = None
        for candidate in existing:
            definition = candidate.definition or {}
            source_slug = str(definition.get("__marketplace_source_slug", "")).strip()
            if source_slug == slug:
                existing_record = candidate
                break

        if existing_record:
            workflow_id = existing_record.id
            already_installed = True
        else:
            definition = dict(row.definition_snapshot or {})
            definition["__marketplace_source_slug"] = slug
            definition["__marketplace_source_id"] = row.id
            definition["__marketplace_version"] = row.version
            created = WorkflowRecord(
                tenant_id=tenant_id,
                name=row.name,
                description=row.description,
                definition=definition,
                created_by=tenant_id,
            )
            session.add(created)
            row.install_count = int(row.install_count or 0) + 1
            session.add(row)
            session.commit()
            session.refresh(created)
            session.refresh(row)
            workflow_id = created.id
            already_installed = False

        profile = session.exec(
            select(CreatorProfile).where(CreatorProfile.user_id == row.creator_id)
        ).first()
        if profile and not already_installed:
            profile.total_installs = int(profile.total_installs or 0) + 1
            session.add(profile)
            session.commit()

    auto_mapped_agents = _ensure_agents_for_workflow(
        tenant_id=tenant_id,
        lineup=row.agent_lineup or [],
        definition_snapshot=row.definition_snapshot or {},
    )

    missing_connectors: list[str] = []
    for connector_id in row.required_connectors or []:
        cid = str(connector_id or "").strip()
        if not cid:
            continue
        try:
            from api.services.connectors.vault import get_binding

            binding = get_binding(tenant_id, cid)
            if not binding or not binding.is_active:
                missing_connectors.append(cid)
        except Exception:
            missing_connectors.append(cid)

    return {
        "installed": True,
        "already_installed": already_installed,
        "workflow_id": workflow_id,
        "name": row.name,
        "missing_connectors": missing_connectors,
        "auto_mapped_agents": auto_mapped_agents,
        "agent_count": len(row.agent_lineup or []),
        "redirect_path": f"/?workflow={workflow_id}",
    }


def _ensure_agents_for_workflow(
    *,
    tenant_id: str,
    lineup: list[dict[str, Any]],
    definition_snapshot: dict[str, Any],
) -> dict[str, str]:
    """Ensure tenant has all agents referenced by workflow steps.

    Returns mapping of step agent IDs to created/reused tenant agent IDs.
    """
    mapped: dict[str, str] = {}
    try:
        from api.schemas.agent_definition.schema import AgentDefinitionSchema
        from api.services.agents import definition_store
    except Exception:
        return mapped

    snapshot_agents = definition_snapshot.get("agents")
    snapshot_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(snapshot_agents, list):
        for row in snapshot_agents:
            if not isinstance(row, dict):
                continue
            agent_id = str(row.get("id") or row.get("agent_id") or "").strip()
            if agent_id:
                snapshot_by_id[agent_id] = row
    elif isinstance(snapshot_agents, dict):
        for key, row in snapshot_agents.items():
            if isinstance(row, dict):
                agent_id = str(row.get("id") or row.get("agent_id") or key or "").strip()
                if agent_id:
                    snapshot_by_id[agent_id] = row

    for row in lineup:
        requested_agent_id = str(row.get("agent_id") or "").strip()
        if not requested_agent_id:
            continue
        existing = definition_store.get_agent(tenant_id, requested_agent_id)
        if existing:
            mapped[requested_agent_id] = requested_agent_id
            continue

        source = snapshot_by_id.get(requested_agent_id, {})
        fallback_name = str(source.get("name") or requested_agent_id).strip() or requested_agent_id
        fallback_description = str(source.get("description") or row.get("description") or "").strip()
        tools = source.get("tools")
        if not isinstance(tools, list):
            tools = []
        required_connectors = source.get("required_connectors")
        if not isinstance(required_connectors, list):
            required_connectors = []
        try:
            schema = AgentDefinitionSchema(
                id=requested_agent_id,
                name=fallback_name[:120],
                description=fallback_description[:500],
                version=str(source.get("version") or "1.0.0"),
                author=str(source.get("author") or ""),
                tags=[str(tag).strip() for tag in (source.get("tags") or []) if str(tag).strip()],
                system_prompt=str(source.get("system_prompt") or ""),
                tools=[str(tool).strip() for tool in tools if str(tool).strip()],
            )
            schema_dict = schema.model_dump(mode="json")
            schema_dict["required_connectors"] = [str(cid).strip() for cid in required_connectors if str(cid).strip()]
            schema = AgentDefinitionSchema.model_validate(schema_dict)
            definition_store.create_agent(tenant_id, tenant_id, schema)
            mapped[requested_agent_id] = requested_agent_id
        except Exception:
            continue
    return mapped


def _to_dict(
    row: PublishedWorkflow,
    *,
    include_definition: bool,
    profile: CreatorProfile | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "slug": row.slug,
        "creator_id": row.creator_id,
        "creator_username": profile.username if profile else "",
        "creator_display_name": profile.display_name if profile else "",
        "creator_avatar_url": profile.avatar_url if profile else "",
        "name": row.name,
        "description": row.description,
        "readme_md": row.readme_md,
        "agent_lineup": row.agent_lineup or [],
        "required_connectors": row.required_connectors or [],
        "screenshots": row.screenshots or [],
        "tags": row.tags or [],
        "category": row.category,
        "version": row.version,
        "status": row.status,
        "install_count": row.install_count,
        "avg_rating": row.avg_rating,
        "review_count": row.review_count,
        "date_created": row.date_created.isoformat() if row.date_created else None,
        "date_updated": row.date_updated.isoformat() if row.date_updated else None,
    }
    if include_definition:
        payload["definition"] = row.definition_snapshot or {}
    return payload
