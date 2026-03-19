"""OG metadata + dynamic preview image endpoints for marketplace shares."""
from __future__ import annotations

import os
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlmodel import Session, select

from api.models.creator_profile import CreatorProfile
from api.services.marketplace.registry import get_marketplace_agent
from api.services.marketplace.workflow_publisher import get_published_workflow
from ktem.db.engine import engine

router = APIRouter(tags=["og-meta"])

_BOT_UA_RE = re.compile(
    r"(bot|crawler|spider|facebookexternalhit|slackbot|discordbot|twitterbot|"
    r"linkedinbot|whatsapp|telegrambot|skypeuripreview)",
    re.IGNORECASE,
)
_FRONTEND_INDEX = Path(__file__).resolve().parents[2] / "frontend" / "user_interface" / "dist" / "index.html"


def _is_bot_request(request: Request) -> bool:
    user_agent = str(request.headers.get("user-agent") or "").strip()
    return bool(_BOT_UA_RE.search(user_agent))


def _public_base_url(request: Request) -> str:
    configured = str(os.getenv("MAIA_PUBLIC_APP_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


def _spa_fallback() -> Response:
    if _FRONTEND_INDEX.exists():
        return FileResponse(_FRONTEND_INDEX)
    return HTMLResponse(
        "<!doctype html><html><body><p>Micrurus frontend is not built.</p></body></html>",
        status_code=200,
    )


def _lookup_creator_name(user_id: str) -> str:
    safe_user_id = str(user_id or "").strip()
    if not safe_user_id:
        return ""
    with Session(engine) as session:
        profile = session.exec(
            select(CreatorProfile).where(CreatorProfile.user_id == safe_user_id)
        ).first()
    if not profile:
        return ""
    return str(profile.display_name or profile.username or "").strip()


def _truncate(value: str, max_len: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1].rstrip()}..."


def _agent_meta(agent_id: str) -> dict[str, str] | None:
    entry = get_marketplace_agent(agent_id)
    if not entry:
        return None
    creator_name = _lookup_creator_name(str(entry.publisher_id or ""))
    title = _truncate(str(entry.name or "Micrurus Agent"), 80)
    description = _truncate(str(entry.description or "Install and run this agent in Micrurus."), 220)
    installs = int(entry.install_count or 0)
    creator = creator_name or "Community creator"
    return {
        "kind": "agents",
        "slug": str(entry.agent_id or agent_id).strip(),
        "title": title,
        "description": description,
        "creator": creator,
        "stats": f"{installs} installs",
        "path": f"/marketplace/agents/{quote(str(entry.agent_id or agent_id).strip())}",
    }


def _team_meta(slug: str) -> dict[str, str] | None:
    row = get_published_workflow(slug)
    if not row:
        return None
    title = _truncate(str(row.get("name") or "Micrurus Team"), 80)
    description = _truncate(
        str(row.get("description") or "Install this workflow team in Micrurus."),
        220,
    )
    creator = str(row.get("creator_display_name") or row.get("creator_username") or "Community creator")
    installs = int(row.get("install_count") or 0)
    return {
        "kind": "teams",
        "slug": str(row.get("slug") or slug).strip(),
        "title": title,
        "description": description,
        "creator": creator,
        "stats": f"{installs} installs",
        "path": f"/marketplace/teams/{quote(str(row.get('slug') or slug).strip())}",
    }


def _render_og_html(request: Request, meta: dict[str, str]) -> str:
    base = _public_base_url(request)
    target_path = str(meta["path"] or "/")
    absolute_path = f"{base}{target_path}"
    image_url = f"{base}/api/og/image/{meta['kind']}/{quote(meta['slug'])}.svg"
    title = escape(meta["title"])
    description = escape(meta["description"])
    creator = escape(meta["creator"])
    stats = escape(meta["stats"])
    target = escape(target_path)
    absolute = escape(absolute_path)
    image = escape(image_url)

    return (
        "<!doctype html>"
        "<html lang='en'><head>"
        "<meta charset='utf-8' />"
        "<meta name='viewport' content='width=device-width, initial-scale=1' />"
        f"<title>{title}</title>"
        f"<meta name='description' content='{description}' />"
        f"<meta property='og:title' content='{title}' />"
        f"<meta property='og:description' content='{description}' />"
        "<meta property='og:type' content='website' />"
        f"<meta property='og:url' content='{absolute}' />"
        f"<meta property='og:image' content='{image}' />"
        "<meta name='twitter:card' content='summary_large_image' />"
        f"<meta name='twitter:title' content='{title}' />"
        f"<meta name='twitter:description' content='{description}' />"
        f"<meta name='twitter:image' content='{image}' />"
        f"<meta name='micrurus:creator' content='{creator}' />"
        f"<meta name='micrurus:stats' content='{stats}' />"
        f"<meta http-equiv='refresh' content='0;url={target}' />"
        "</head><body>"
        f"<script>window.location.replace({target_path!r});</script>"
        "</body></html>"
    )


def _render_og_svg(*, title: str, subtitle: str, footer: str) -> str:
    safe_title = escape(_truncate(title, 72))
    safe_subtitle = escape(_truncate(subtitle, 120))
    safe_footer = escape(_truncate(footer, 64))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#111827"/>
      <stop offset="100%" stop-color="#1d4ed8"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <circle cx="1080" cy="90" r="120" fill="rgba(255,255,255,0.08)"/>
  <circle cx="120" cy="560" r="160" fill="rgba(255,255,255,0.06)"/>
  <text x="80" y="110" fill="#dbeafe" font-size="30" font-family="Inter,Segoe UI,Arial,sans-serif">Micrurus Marketplace</text>
  <text x="80" y="220" fill="#ffffff" font-size="64" font-weight="700" font-family="Inter,Segoe UI,Arial,sans-serif">{safe_title}</text>
  <text x="80" y="300" fill="#c7d2fe" font-size="32" font-family="Inter,Segoe UI,Arial,sans-serif">{safe_subtitle}</text>
  <rect x="80" y="460" width="1040" height="80" rx="16" fill="rgba(15,23,42,0.4)" stroke="rgba(255,255,255,0.25)"/>
  <text x="110" y="510" fill="#bfdbfe" font-size="32" font-family="Inter,Segoe UI,Arial,sans-serif">{safe_footer}</text>
</svg>"""


@router.get("/marketplace/agents/{agent_id}", include_in_schema=False)
def marketplace_agent_page(agent_id: str, request: Request) -> Response:
    if not _is_bot_request(request):
        return _spa_fallback()
    meta = _agent_meta(agent_id)
    if not meta:
        return _spa_fallback()
    return HTMLResponse(_render_og_html(request, meta))


@router.get("/marketplace/teams/{slug}", include_in_schema=False)
def marketplace_team_page(slug: str, request: Request) -> Response:
    if not _is_bot_request(request):
        return _spa_fallback()
    meta = _team_meta(slug)
    if not meta:
        return _spa_fallback()
    return HTMLResponse(_render_og_html(request, meta))


@router.get("/api/og/image/agents/{agent_id}.svg", include_in_schema=False)
def marketplace_agent_og_image(agent_id: str) -> Response:
    meta = _agent_meta(agent_id)
    if not meta:
        return Response(status_code=404)
    svg = _render_og_svg(
        title=meta["title"],
        subtitle=meta["description"],
        footer=f"{meta['creator']} - {meta['stats']}",
    )
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/api/og/image/teams/{slug}.svg", include_in_schema=False)
def marketplace_team_og_image(slug: str) -> Response:
    meta = _team_meta(slug)
    if not meta:
        return Response(status_code=404)
    svg = _render_og_svg(
        title=meta["title"],
        subtitle=meta["description"],
        footer=f"{meta['creator']} - {meta['stats']}",
    )
    return Response(content=svg, media_type="image/svg+xml")
