from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from threading import Lock


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _db_path(default_path: Path | None = None) -> Path:
    path = default_path or (Path(".maia_agent") / "google_oauth.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class GoogleTokenRecord:
    user_id: str
    access_token: str
    refresh_token: str
    token_type: str
    scopes: list[str]
    expires_at: str | None
    id_token: str | None
    email: str | None
    date_updated: str

    def is_expired(self, *, leeway_seconds: int = 90) -> bool:
        expires_at_dt = _parse_iso(self.expires_at)
        if expires_at_dt is None:
            return False
        return expires_at_dt <= (_utc_now() + timedelta(seconds=max(0, int(leeway_seconds))))


@dataclass
class OAuthStateRecord:
    state: str
    user_id: str
    redirect_uri: str
    scopes: list[str]
    created_at: str
    expires_at: str

    def expired(self) -> bool:
        expires_at_dt = _parse_iso(self.expires_at)
        if expires_at_dt is None:
            return True
        return _utc_now() > expires_at_dt


class _SqliteStore:
    def __init__(self, *, path: Path | None = None) -> None:
        self._path = _db_path(path)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._path), check_same_thread=False)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS google_tokens (
                    user_id TEXT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    token_type TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    expires_at TEXT NULL,
                    id_token TEXT NULL,
                    email TEXT NULL,
                    date_updated TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS google_oauth_states (
                    state TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            conn.commit()


class GoogleTokenStore:
    def __init__(self, *, path: Path | None = None) -> None:
        self._db = _SqliteStore(path=path)

    def get_tokens(self, *, user_id: str) -> GoogleTokenRecord | None:
        with self._db._lock, self._db._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id, access_token, refresh_token, token_type, scopes_json,
                       expires_at, id_token, email, date_updated
                FROM google_tokens
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        scopes = []
        try:
            parsed = json.loads(str(row[4] or "[]"))
            if isinstance(parsed, list):
                scopes = [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            scopes = []
        record = GoogleTokenRecord(
            user_id=str(row[0]),
            access_token=str(row[1] or ""),
            refresh_token=str(row[2] or ""),
            token_type=str(row[3] or "Bearer"),
            scopes=scopes,
            expires_at=str(row[5]) if row[5] else None,
            id_token=str(row[6]) if row[6] else None,
            email=str(row[7]) if row[7] else None,
            date_updated=str(row[8] or _iso_now()),
        )
        if not record.access_token:
            return None
        return record

    def save_tokens(
        self,
        *,
        user_id: str,
        access_token: str,
        refresh_token: str = "",
        token_type: str = "Bearer",
        scopes: list[str] | None = None,
        expires_in: int | None = None,
        expires_at: str | None = None,
        id_token: str | None = None,
        email: str | None = None,
    ) -> GoogleTokenRecord:
        previous = self.get_tokens(user_id=user_id)
        final_refresh_token = refresh_token.strip() or (previous.refresh_token if previous else "")
        final_scopes = scopes if scopes is not None else (previous.scopes if previous else [])
        final_expires_at = expires_at
        if not final_expires_at and expires_in is not None:
            final_expires_at = (_utc_now() + timedelta(seconds=max(0, int(expires_in)))).isoformat()
        if not final_expires_at and previous is not None:
            final_expires_at = previous.expires_at
        final_id_token = id_token if id_token is not None else (previous.id_token if previous else None)
        final_email = email if email is not None else (previous.email if previous else None)

        record = GoogleTokenRecord(
            user_id=user_id,
            access_token=access_token.strip(),
            refresh_token=final_refresh_token,
            token_type=(token_type or "Bearer").strip() or "Bearer",
            scopes=list(dict.fromkeys([item for item in (final_scopes or []) if item])),
            expires_at=final_expires_at,
            id_token=final_id_token,
            email=final_email,
            date_updated=_iso_now(),
        )

        with self._db._lock, self._db._connect() as conn:
            conn.execute(
                """
                INSERT INTO google_tokens (
                    user_id, access_token, refresh_token, token_type, scopes_json,
                    expires_at, id_token, email, date_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    access_token=excluded.access_token,
                    refresh_token=excluded.refresh_token,
                    token_type=excluded.token_type,
                    scopes_json=excluded.scopes_json,
                    expires_at=excluded.expires_at,
                    id_token=excluded.id_token,
                    email=excluded.email,
                    date_updated=excluded.date_updated
                """,
                (
                    record.user_id,
                    record.access_token,
                    record.refresh_token,
                    record.token_type,
                    json.dumps(record.scopes),
                    record.expires_at,
                    record.id_token,
                    record.email,
                    record.date_updated,
                ),
            )
            conn.commit()
        return record

    def clear_tokens(self, *, user_id: str) -> bool:
        with self._db._lock, self._db._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM google_tokens WHERE user_id = ?",
                (user_id,),
            )
            conn.commit()
            return int(cursor.rowcount or 0) > 0


class OAuthStateStore:
    def __init__(self, *, path: Path | None = None, ttl_seconds: int = 900) -> None:
        self._db = _SqliteStore(path=path)
        self._ttl_seconds = max(60, int(ttl_seconds))

    def create_state(
        self,
        *,
        state: str,
        user_id: str,
        redirect_uri: str,
        scopes: list[str],
    ) -> OAuthStateRecord:
        created_at = _utc_now()
        record = OAuthStateRecord(
            state=state,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=list(dict.fromkeys([item for item in scopes if item])),
            created_at=created_at.isoformat(),
            expires_at=(created_at + timedelta(seconds=self._ttl_seconds)).isoformat(),
        )
        with self._db._lock, self._db._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO google_oauth_states (
                    state, user_id, redirect_uri, scopes_json, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.state,
                    record.user_id,
                    record.redirect_uri,
                    json.dumps(record.scopes),
                    record.created_at,
                    record.expires_at,
                ),
            )
            conn.commit()
        return record

    def consume_state(self, *, state: str) -> OAuthStateRecord | None:
        with self._db._lock, self._db._connect() as conn:
            row = conn.execute(
                """
                SELECT state, user_id, redirect_uri, scopes_json, created_at, expires_at
                FROM google_oauth_states
                WHERE state = ?
                """,
                (state,),
            ).fetchone()
            conn.execute("DELETE FROM google_oauth_states WHERE state = ?", (state,))
            conn.commit()
        if row is None:
            return None
        scopes = []
        try:
            parsed = json.loads(str(row[3] or "[]"))
            if isinstance(parsed, list):
                scopes = [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            scopes = []
        record = OAuthStateRecord(
            state=str(row[0]),
            user_id=str(row[1]),
            redirect_uri=str(row[2] or ""),
            scopes=scopes,
            created_at=str(row[4] or _iso_now()),
            expires_at=str(row[5] or _iso_now()),
        )
        if record.expired():
            return None
        return record

    def purge_expired(self) -> int:
        now_iso = _iso_now()
        with self._db._lock, self._db._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM google_oauth_states WHERE expires_at <= ?",
                (now_iso,),
            )
            conn.commit()
            return int(cursor.rowcount or 0)


_token_store: GoogleTokenStore | None = None
_state_store: OAuthStateStore | None = None


def get_google_token_store() -> GoogleTokenStore:
    global _token_store
    if _token_store is None:
        _token_store = GoogleTokenStore()
    return _token_store


def get_oauth_state_store() -> OAuthStateStore:
    global _state_store
    if _state_store is None:
        _state_store = OAuthStateStore()
    return _state_store
