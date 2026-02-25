from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from api.services.agent.models import utc_now


def _audit_path() -> Path:
    root = Path(".maia_agent")
    root.mkdir(parents=True, exist_ok=True)
    return root / "audit.log"


class AuditLogger:
    def __init__(self) -> None:
        self._lock = Lock()

    def _redact(self, payload: dict[str, Any]) -> dict[str, Any]:
        def redact_value(key: str, value: Any) -> Any:
            lowered = key.lower()
            if any(token in lowered for token in ("token", "password", "secret", "api_key")):
                return "***"
            if isinstance(value, dict):
                return {k: redact_value(str(k), v) for k, v in value.items()}
            if isinstance(value, list):
                return [redact_value(key, item) for item in value]
            return value

        return {key: redact_value(str(key), value) for key, value in payload.items()}

    def write(
        self,
        *,
        user_id: str,
        tenant_id: str,
        run_id: str | None,
        event: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        row = {
            "timestamp": utc_now().isoformat(),
            "user_id": user_id,
            "tenant_id": tenant_id,
            "run_id": run_id,
            "event": event,
            "payload": self._redact(payload or {}),
        }
        with self._lock:
            with _audit_path().open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row))
                handle.write("\n")


_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
