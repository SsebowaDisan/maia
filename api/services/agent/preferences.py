from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any


def _prefs_path() -> Path:
    root = Path(".maia_agent")
    root.mkdir(parents=True, exist_ok=True)
    return root / "user_preferences.json"


class UserPreferenceStore:
    def __init__(self) -> None:
        self.file_path = _prefs_path()
        self._lock = Lock()
        if not self.file_path.exists():
            self.file_path.write_text("{}", encoding="utf-8")

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.file_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _save(self, payload: dict[str, dict[str, Any]]) -> None:
        self.file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get(self, user_id: str) -> dict[str, Any]:
        payload = self._load()
        current = payload.get(str(user_id), {})
        return dict(current) if isinstance(current, dict) else {}

    def merge(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        safe_patch = {
            key: str(value).strip()[:80]
            for key, value in (patch or {}).items()
            if isinstance(key, str) and str(value or "").strip()
        }
        if not safe_patch:
            return self.get(user_id)
        with self._lock:
            payload = self._load()
            current = payload.get(str(user_id), {})
            if not isinstance(current, dict):
                current = {}
            merged = {**current, **safe_patch}
            payload[str(user_id)] = merged
            self._save(payload)
            return merged


_store: UserPreferenceStore | None = None


def get_user_preference_store() -> UserPreferenceStore:
    global _store
    if _store is None:
        _store = UserPreferenceStore()
    return _store
