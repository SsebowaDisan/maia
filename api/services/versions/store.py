"""Version store -- create, query, promote and rollback version records.

All write operations create new immutable rows; no existing row is ever
mutated except for the ``is_latest`` flag.
"""
from __future__ import annotations

import time
import uuid

from fastapi import HTTPException, status
from sqlmodel import Session, select

from api.models.version_history import VersionRecord
from ktem.db.engine import engine


# ── Helpers ───────────────────────────────────────────────────────────────────


def next_version(current: str) -> str:
    """Bump the patch component of a semver string.

    ``"1.0.0"`` -> ``"1.0.1"``
    """
    parts = current.split(".")
    if len(parts) != 3:
        parts = ["1", "0", "0"]
    major, minor, patch = parts
    return f"{major}.{minor}.{int(patch) + 1}"


def _clear_latest(
    session: Session,
    resource_type: str,
    resource_id: str,
    environment: str,
) -> None:
    """Set ``is_latest=False`` for all existing records matching the key."""
    stmt = select(VersionRecord).where(
        VersionRecord.resource_type == resource_type,
        VersionRecord.resource_id == resource_id,
        VersionRecord.environment == environment,
        VersionRecord.is_latest == True,  # noqa: E712
    )
    for rec in session.exec(stmt).all():
        rec.is_latest = False
        session.add(rec)


# ── Public API ────────────────────────────────────────────────────────────────


def create_version(
    resource_type: str,
    resource_id: str,
    tenant_id: str,
    version: str,
    definition: str,
    *,
    created_by: str,
    environment: str = "dev",
    changelog: str = "",
) -> VersionRecord:
    """Persist a new immutable version record."""
    record = VersionRecord(
        id=uuid.uuid4().hex,
        resource_type=resource_type,
        resource_id=resource_id,
        tenant_id=tenant_id,
        version=version,
        environment=environment,
        definition_json=definition,
        created_by=created_by,
        created_at=time.time(),
        changelog=changelog,
        is_latest=True,
    )
    with Session(engine) as session:
        _clear_latest(session, resource_type, resource_id, environment)
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def get_version(
    resource_type: str,
    resource_id: str,
    version: str,
    environment: str = "dev",
) -> VersionRecord | None:
    """Return a specific version or ``None``."""
    with Session(engine) as session:
        stmt = select(VersionRecord).where(
            VersionRecord.resource_type == resource_type,
            VersionRecord.resource_id == resource_id,
            VersionRecord.version == version,
            VersionRecord.environment == environment,
        )
        return session.exec(stmt).first()


def get_latest_version(
    resource_type: str,
    resource_id: str,
    environment: str = "dev",
) -> VersionRecord | None:
    """Return the latest version for a resource + environment."""
    with Session(engine) as session:
        stmt = (
            select(VersionRecord)
            .where(
                VersionRecord.resource_type == resource_type,
                VersionRecord.resource_id == resource_id,
                VersionRecord.environment == environment,
                VersionRecord.is_latest == True,  # noqa: E712
            )
            .order_by(VersionRecord.created_at.desc())  # type: ignore[union-attr]
            .limit(1)
        )
        return session.exec(stmt).first()


def list_versions(
    resource_type: str,
    resource_id: str,
    *,
    environment: str | None = None,
    limit: int = 50,
) -> list[VersionRecord]:
    """Return versions newest-first, optionally filtered by environment."""
    with Session(engine) as session:
        stmt = (
            select(VersionRecord)
            .where(
                VersionRecord.resource_type == resource_type,
                VersionRecord.resource_id == resource_id,
            )
            .order_by(VersionRecord.created_at.desc())  # type: ignore[union-attr]
            .limit(limit)
        )
        if environment is not None:
            stmt = stmt.where(VersionRecord.environment == environment)
        return list(session.exec(stmt).all())


def promote(
    resource_type: str,
    resource_id: str,
    from_env: str,
    to_env: str,
    *,
    promoted_by: str,
) -> VersionRecord:
    """Copy the latest version from *from_env* to *to_env*."""
    source = get_latest_version(resource_type, resource_id, environment=from_env)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No version found in {from_env} for {resource_type}/{resource_id}.",
        )
    # Determine next version in the target environment
    target_latest = get_latest_version(resource_type, resource_id, environment=to_env)
    new_ver = next_version(target_latest.version) if target_latest else source.version

    return create_version(
        resource_type=resource_type,
        resource_id=resource_id,
        tenant_id=source.tenant_id,
        version=new_ver,
        definition=source.definition_json,
        created_by=promoted_by,
        environment=to_env,
        changelog=f"Promoted from {from_env} (v{source.version})",
    )


def rollback(
    resource_type: str,
    resource_id: str,
    target_version: str,
    environment: str,
    *,
    rolled_back_by: str,
) -> VersionRecord:
    """Create a new version that restores *target_version*."""
    source = get_version(resource_type, resource_id, target_version, environment)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {target_version} not found in {environment}.",
        )
    current = get_latest_version(resource_type, resource_id, environment)
    new_ver = next_version(current.version) if current else next_version(source.version)

    return create_version(
        resource_type=resource_type,
        resource_id=resource_id,
        tenant_id=source.tenant_id,
        version=new_ver,
        definition=source.definition_json,
        created_by=rolled_back_by,
        environment=environment,
        changelog=f"Rollback to v{target_version}",
    )
