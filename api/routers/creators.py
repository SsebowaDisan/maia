"""Creator profile API for marketplace publishers."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlmodel import Session, SQLModel, col, select

from api.auth import get_current_user_id
from api.models.creator_follow import CreatorFollow
from api.models.creator_profile import CreatorProfile, validate_username
from api.services.auth.tokens import TokenError, decode_access_token
from api.services.marketplace.feed import list_creator_activity, list_feed_for_user
from ktem.db.engine import engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/creators", tags=["creators"])
_bearer = HTTPBearer(auto_error=False)
_AVATAR_ROOT = Path(".maia_agent") / "creator_avatars"


class CreateProfileRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    display_name: str = Field(default="", max_length=80)
    bio: str = Field(default="", max_length=300)
    website_url: str = Field(default="", max_length=300)
    github_url: str = Field(default="", max_length=300)
    twitter_url: str = Field(default="", max_length=300)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    website_url: str | None = None
    github_url: str | None = None
    twitter_url: str | None = None


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def _normalize_url(value: str, *, max_len: int) -> str:
    return str(value or "").strip()[:max_len]


def _profile_to_dict(
    profile: CreatorProfile,
    *,
    is_following: bool | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": profile.id,
        "user_id": profile.user_id,
        "username": profile.username,
        "display_name": profile.display_name,
        "bio": profile.bio,
        "avatar_url": profile.avatar_url,
        "website_url": profile.website_url,
        "github_url": profile.github_url,
        "twitter_url": profile.twitter_url,
        "follower_count": int(profile.follower_count or 0),
        "total_installs": int(profile.total_installs or 0),
        "published_agent_count": int(profile.published_agent_count or 0),
        "published_team_count": int(profile.published_team_count or 0),
        "date_created": profile.date_created.isoformat() if profile.date_created else None,
        "date_updated": profile.date_updated.isoformat() if profile.date_updated else None,
    }
    if is_following is not None:
        payload["is_following"] = bool(is_following)
    return payload


def _resolve_optional_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    user_id_query: Annotated[str | None, Query(alias="user_id")] = None,
) -> str | None:
    direct = str(x_user_id or user_id_query or "").strip()
    if direct:
        return direct
    if not credentials or not credentials.credentials:
        return None
    token = str(credentials.credentials).strip()
    if not token or token.startswith("mk_"):
        return None
    try:
        payload = decode_access_token(token)
    except TokenError:
        return None
    subject = str(payload.get("sub") or "").strip()
    return subject or None


def _sanitize_upload_name(name: str) -> str:
    base = Path(str(name or "avatar").strip()).name.lower()
    base = re.sub(r"[^a-z0-9._-]+", "-", base).strip("-")
    if not base:
        return "avatar.png"
    return base[:90]


def _resolve_creator_profile(session: Session, username: str) -> CreatorProfile:
    profile = session.exec(
        select(CreatorProfile).where(CreatorProfile.username == username.strip().lower())
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Creator not found.")
    return profile


@router.get("/me")
def get_my_profile(user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    _ensure_tables()
    with Session(engine) as session:
        profile = session.exec(
            select(CreatorProfile).where(CreatorProfile.user_id == user_id)
        ).first()
    if not profile:
        return {"exists": False}
    return {**_profile_to_dict(profile), "exists": True}


@router.get("/me/stats")
def get_my_creator_stats(user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    _ensure_tables()
    with Session(engine) as session:
        profile = session.exec(
            select(CreatorProfile).where(CreatorProfile.user_id == user_id)
        ).first()
    if not profile:
        return {
            "total_installs": 0,
            "published_agent_count": 0,
            "published_team_count": 0,
            "top_agents": [],
            "top_teams": [],
        }

    top_agents: list[dict[str, Any]] = []
    try:
        from api.routers.marketplace import _list_marketplace_agents_by_publisher

        rows = _list_marketplace_agents_by_publisher(user_id)
        rows.sort(key=lambda row: int(row.get("install_count") or 0), reverse=True)
        top_agents = rows[:5]
    except Exception:
        top_agents = []

    top_teams = []
    try:
        from api.services.marketplace.workflow_publisher import list_published_workflows

        rows = list_published_workflows(creator_id=user_id, limit=50)
        rows.sort(key=lambda row: int(row.get("install_count") or 0), reverse=True)
        top_teams = rows[:5]
    except Exception:
        top_teams = []

    return {
        "total_installs": int(profile.total_installs or 0),
        "published_agent_count": int(profile.published_agent_count or 0),
        "published_team_count": int(profile.published_team_count or 0),
        "follower_count": int(profile.follower_count or 0),
        "top_agents": top_agents,
        "top_teams": top_teams,
    }


@router.post("/me", status_code=status.HTTP_201_CREATED)
def create_my_profile(
    body: CreateProfileRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _ensure_tables()
    username = validate_username(body.username)
    with Session(engine) as session:
        existing = session.exec(
            select(CreatorProfile).where(
                (CreatorProfile.user_id == user_id) | (CreatorProfile.username == username)
            )
        ).first()
        if existing:
            if existing.user_id == user_id:
                raise HTTPException(status_code=409, detail="Profile already exists. Use PUT to update.")
            raise HTTPException(status_code=409, detail="Username is already taken.")

        profile = CreatorProfile(
            user_id=user_id,
            username=username,
            display_name=body.display_name.strip()[:80],
            bio=body.bio.strip()[:300],
            website_url=_normalize_url(body.website_url, max_len=300),
            github_url=_normalize_url(body.github_url, max_len=300),
            twitter_url=_normalize_url(body.twitter_url, max_len=300),
            date_created=datetime.utcnow(),
            date_updated=datetime.utcnow(),
        )
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return _profile_to_dict(profile)


@router.put("/me")
def update_my_profile(
    body: UpdateProfileRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _ensure_tables()
    with Session(engine) as session:
        profile = session.exec(
            select(CreatorProfile).where(CreatorProfile.user_id == user_id)
        ).first()
        if not profile:
            raise HTTPException(status_code=404, detail="No profile found. Create one first.")

        if body.display_name is not None:
            profile.display_name = body.display_name.strip()[:80]
        if body.bio is not None:
            profile.bio = body.bio.strip()[:300]
        if body.avatar_url is not None:
            profile.avatar_url = _normalize_url(body.avatar_url, max_len=500)
        if body.website_url is not None:
            profile.website_url = _normalize_url(body.website_url, max_len=300)
        if body.github_url is not None:
            profile.github_url = _normalize_url(body.github_url, max_len=300)
        if body.twitter_url is not None:
            profile.twitter_url = _normalize_url(body.twitter_url, max_len=300)

        profile.date_updated = datetime.utcnow()
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return _profile_to_dict(profile)


@router.post("/me/avatar")
async def upload_my_avatar(
    avatar: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _ensure_tables()
    content_type = str(avatar.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Avatar must be an image.")

    _AVATAR_ROOT.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_upload_name(avatar.filename or "avatar.png")
    ext = Path(safe_name).suffix or ".png"
    file_name = f"{user_id}-{uuid.uuid4().hex[:10]}{ext}"
    target = _AVATAR_ROOT / file_name

    payload = await avatar.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Avatar file was empty.")
    if len(payload) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Avatar file must be <= 5MB.")
    target.write_bytes(payload)

    avatar_url = f"/api/creators/avatars/{file_name}"
    with Session(engine) as session:
        profile = session.exec(
            select(CreatorProfile).where(CreatorProfile.user_id == user_id)
        ).first()
        if not profile:
            seed = re.sub(r"[^a-z0-9]+", "-", str(user_id).lower()).strip("-")[:20]
            if len(seed) < 3:
                seed = f"creator{uuid.uuid4().hex[:3]}"
            seed = re.sub(r"[^a-z0-9]+", "-", seed).strip("-")
            candidate = f"{seed}-{uuid.uuid4().hex[:4]}"
            username = validate_username(candidate)
            profile = CreatorProfile(
                user_id=user_id,
                username=username,
                display_name=f"Creator {user_id[:8]}",
                avatar_url=avatar_url,
                date_created=datetime.utcnow(),
                date_updated=datetime.utcnow(),
            )
        else:
            profile.avatar_url = avatar_url
            profile.date_updated = datetime.utcnow()
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return {"avatar_url": avatar_url, "profile": _profile_to_dict(profile)}


@router.get("/me/following")
def list_my_following(
    user_id: str = Depends(get_current_user_id),
    limit: int = 100,
) -> list[dict[str, Any]]:
    _ensure_tables()
    cap = min(max(limit, 1), 300)
    with Session(engine) as session:
        rows = session.exec(
            select(CreatorFollow)
            .where(CreatorFollow.follower_user_id == user_id)
            .order_by(col(CreatorFollow.date_created).desc())
            .limit(cap)
        ).all()
        creator_ids = [row.creator_user_id for row in rows]
        creators = {
            profile.user_id: profile
            for profile in session.exec(
                select(CreatorProfile).where(CreatorProfile.user_id.in_(creator_ids))
            ).all()
        }
    results: list[dict[str, Any]] = []
    for row in rows:
        creator = creators.get(row.creator_user_id)
        results.append(
            {
                "user_id": row.creator_user_id,
                "username": creator.username if creator else "",
                "display_name": creator.display_name if creator else "",
                "avatar_url": creator.avatar_url if creator else "",
                "date_created": row.date_created.isoformat() if row.date_created else "",
            }
        )
    return results


@router.get("/me/feed")
def get_my_feed(user_id: str = Depends(get_current_user_id), limit: int = 30) -> list[dict[str, Any]]:
    _ensure_tables()
    return list_feed_for_user(user_id, limit=min(max(limit, 1), 100))


@router.get("/avatars/{avatar_name}")
def get_avatar_file(avatar_name: str) -> FileResponse:
    safe_name = _sanitize_upload_name(avatar_name)
    target = (_AVATAR_ROOT / safe_name).resolve()
    root = _AVATAR_ROOT.resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=404, detail="Avatar not found.")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Avatar not found.")
    return FileResponse(target)


@router.get("/{username}")
def get_creator_profile(
    username: str,
    viewer_user_id: str | None = Depends(_resolve_optional_user_id),
) -> dict[str, Any]:
    _ensure_tables()
    with Session(engine) as session:
        profile = _resolve_creator_profile(session, username)
        is_following = None
        if viewer_user_id:
            followed = session.exec(
                select(CreatorFollow).where(
                    CreatorFollow.follower_user_id == viewer_user_id,
                    CreatorFollow.creator_user_id == profile.user_id,
                )
            ).first()
            is_following = bool(followed)
    return _profile_to_dict(profile, is_following=is_following)


@router.get("/{username}/agents")
def list_creator_agents(username: str) -> list[dict[str, Any]]:
    _ensure_tables()
    with Session(engine) as session:
        profile = _resolve_creator_profile(session, username)
    try:
        from api.routers.marketplace import _list_marketplace_agents_by_publisher

        return _list_marketplace_agents_by_publisher(profile.user_id)
    except Exception:
        return []


@router.get("/{username}/teams")
def list_creator_teams(username: str, limit: int = 50) -> list[dict[str, Any]]:
    _ensure_tables()
    with Session(engine) as session:
        profile = _resolve_creator_profile(session, username)
    try:
        from api.services.marketplace.workflow_publisher import list_published_workflows

        return list_published_workflows(creator_id=profile.user_id, limit=min(limit, 100))
    except Exception:
        return []


@router.get("/{username}/activity")
def get_creator_activity(username: str, limit: int = 30) -> list[dict[str, Any]]:
    _ensure_tables()
    with Session(engine) as session:
        profile = _resolve_creator_profile(session, username)
    return list_creator_activity(profile.user_id, limit=min(max(limit, 1), 100))


@router.get("/{username}/followers")
def list_creator_followers(username: str, limit: int = 50) -> list[dict[str, Any]]:
    _ensure_tables()
    cap = min(max(limit, 1), 200)
    with Session(engine) as session:
        profile = _resolve_creator_profile(session, username)
        rows = session.exec(
            select(CreatorFollow)
            .where(CreatorFollow.creator_user_id == profile.user_id)
            .order_by(col(CreatorFollow.date_created).desc())
            .limit(cap)
        ).all()
        follower_ids = [row.follower_user_id for row in rows]
        follower_profiles = {
            entry.user_id: entry
            for entry in session.exec(
                select(CreatorProfile).where(CreatorProfile.user_id.in_(follower_ids))
            ).all()
        }
    results: list[dict[str, Any]] = []
    for row in rows:
        follower = follower_profiles.get(row.follower_user_id)
        results.append(
            {
                "user_id": row.follower_user_id,
                "username": follower.username if follower else "",
                "display_name": follower.display_name if follower else "",
                "avatar_url": follower.avatar_url if follower else "",
                "date_created": row.date_created.isoformat() if row.date_created else "",
            }
        )
    return results
