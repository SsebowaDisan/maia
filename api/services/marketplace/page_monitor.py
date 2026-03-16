"""Page monitor service — fetch, diff, and store page snapshots for the Competitor Change Radar.

Responsibility:
- Store/update URL baselines per (tenant_id, agent_id, url)
- Compute SHA-256 hash of extracted page text and detect changes
- Background thread that re-fetches active URLs on a configurable interval
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from datetime import datetime
from threading import Event, Thread
from typing import NamedTuple

import httpx
from sqlmodel import Session, select

from api.context import get_context
from api.models.page_snapshot import PageSnapshotRecord

logger = logging.getLogger(__name__)

# Default re-fetch interval: 6 hours
_DEFAULT_INTERVAL_SECS = 6 * 3600
_MAX_TEXT_BYTES = 65_536  # ~64 KB stored per snapshot


# ── Text extraction ───────────────────────────────────────────────────────────


def _extract_text(html: str) -> str:
    """Very lightweight HTML → plain-text extraction (no heavy deps required)."""
    # Remove script/style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_TEXT_BYTES]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ── Snapshot helpers ──────────────────────────────────────────────────────────


class SnapshotDiff(NamedTuple):
    url: str
    old_hash: str
    new_hash: str
    changed: bool


def fetch_page_text(url: str, timeout: int = 15) -> str:
    """Fetch a URL and return its extracted plain text."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; MaiaBot/1.0; +https://maia.ai/bot)"
        )
    }
    resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type:
        return resp.text[:_MAX_TEXT_BYTES]
    return _extract_text(resp.text)


def upsert_snapshot(
    tenant_id: str,
    agent_id: str,
    url: str,
    session: Session,
) -> SnapshotDiff:
    """Fetch the page, compare to stored baseline, and update the DB row."""
    try:
        new_text = fetch_page_text(url)
    except Exception as exc:
        logger.warning("page_monitor: failed to fetch %s — %s", url, exc)
        return SnapshotDiff(url=url, old_hash="", new_hash="", changed=False)

    new_hash = _sha256(new_text)

    existing = session.exec(
        select(PageSnapshotRecord).where(
            PageSnapshotRecord.tenant_id == tenant_id,
            PageSnapshotRecord.agent_id == agent_id,
            PageSnapshotRecord.url == url,
            PageSnapshotRecord.is_active == True,  # noqa: E712
        )
    ).first()

    if existing:
        old_hash = existing.content_hash
        changed = old_hash != new_hash
        if changed:
            existing.content_hash = new_hash
            existing.content_text = new_text
            existing.last_fetched_at = datetime.utcnow()
            session.add(existing)
            session.commit()
            logger.info("page_monitor: change detected for %s", url)
        return SnapshotDiff(url=url, old_hash=old_hash, new_hash=new_hash, changed=changed)
    else:
        record = PageSnapshotRecord(
            tenant_id=tenant_id,
            agent_id=agent_id,
            url=url,
            content_hash=new_hash,
            content_text=new_text,
        )
        session.add(record)
        session.commit()
        return SnapshotDiff(url=url, old_hash="", new_hash=new_hash, changed=False)


def add_monitored_url(tenant_id: str, agent_id: str, url: str, session: Session) -> PageSnapshotRecord:
    """Add a URL to the monitor list (or reactivate a soft-deleted one)."""
    existing = session.exec(
        select(PageSnapshotRecord).where(
            PageSnapshotRecord.tenant_id == tenant_id,
            PageSnapshotRecord.agent_id == agent_id,
            PageSnapshotRecord.url == url,
        )
    ).first()
    if existing:
        existing.is_active = True
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    record = PageSnapshotRecord(tenant_id=tenant_id, agent_id=agent_id, url=url)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def remove_monitored_url(tenant_id: str, agent_id: str, url: str, session: Session) -> bool:
    """Soft-delete a monitored URL."""
    record = session.exec(
        select(PageSnapshotRecord).where(
            PageSnapshotRecord.tenant_id == tenant_id,
            PageSnapshotRecord.agent_id == agent_id,
            PageSnapshotRecord.url == url,
            PageSnapshotRecord.is_active == True,  # noqa: E712
        )
    ).first()
    if not record:
        return False
    record.is_active = False
    session.add(record)
    session.commit()
    return True


def list_monitored_urls(tenant_id: str, agent_id: str, session: Session) -> list[PageSnapshotRecord]:
    """Return all active monitored URLs for a given tenant + agent."""
    return list(
        session.exec(
            select(PageSnapshotRecord).where(
                PageSnapshotRecord.tenant_id == tenant_id,
                PageSnapshotRecord.agent_id == agent_id,
                PageSnapshotRecord.is_active == True,  # noqa: E712
            )
        ).all()
    )


# ── Background monitor thread ─────────────────────────────────────────────────


class PageMonitor:
    """Background thread that periodically re-fetches all active page snapshots."""

    def __init__(self, interval_secs: int = _DEFAULT_INTERVAL_SECS) -> None:
        self._interval = interval_secs
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._loop,
            daemon=True,
            name="maia-page-monitor",
        )
        self._thread.start()
        logger.info("PageMonitor started (interval=%ds)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._run_cycle()
            except Exception as exc:
                logger.error("PageMonitor cycle failed: %s", exc, exc_info=True)

    def _run_cycle(self) -> None:
        ctx = get_context()
        with Session(ctx.engine) as session:
            records = session.exec(
                select(PageSnapshotRecord).where(PageSnapshotRecord.is_active == True)  # noqa: E712
            ).all()
            for record in records:
                try:
                    upsert_snapshot(record.tenant_id, record.agent_id, record.url, session)
                except Exception as exc:
                    logger.warning("PageMonitor: error processing %s — %s", record.url, exc)


_monitor: PageMonitor | None = None
_lock = threading.Lock()


def get_page_monitor() -> PageMonitor:
    global _monitor
    with _lock:
        if _monitor is None:
            _monitor = PageMonitor()
    return _monitor
