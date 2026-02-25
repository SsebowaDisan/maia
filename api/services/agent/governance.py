from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any


def _path() -> Path:
    root = Path(".maia_agent")
    root.mkdir(parents=True, exist_ok=True)
    return root / "governance.json"


class GovernanceService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._file = _path()
        if not self._file.exists():
            self._file.write_text(
                json.dumps(
                    {
                        "global_kill_switch": False,
                        "tool_flags": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self._file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"global_kill_switch": False, "tool_flags": {}}

    def _save(self, payload: dict[str, Any]) -> None:
        self._file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get(self) -> dict[str, Any]:
        return self._load()

    def set_global_kill_switch(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            payload = self._load()
            payload["global_kill_switch"] = bool(enabled)
            self._save(payload)
            return payload

    def set_tool_enabled(self, tool_id: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            payload = self._load()
            tool_flags = payload.get("tool_flags")
            if not isinstance(tool_flags, dict):
                tool_flags = {}
            tool_flags[tool_id] = bool(enabled)
            payload["tool_flags"] = tool_flags
            self._save(payload)
            return payload

    def is_tool_enabled(self, tool_id: str) -> bool:
        payload = self._load()
        if bool(payload.get("global_kill_switch")):
            return False
        tool_flags = payload.get("tool_flags")
        if isinstance(tool_flags, dict) and tool_id in tool_flags:
            return bool(tool_flags[tool_id])
        return True


_service: GovernanceService | None = None


def get_governance_service() -> GovernanceService:
    global _service
    if _service is None:
        _service = GovernanceService()
    return _service
