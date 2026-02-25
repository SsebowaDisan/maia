from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from threading import Lock
from typing import Any

from api.services.agent.models import utc_now


@dataclass
class ConnectorCredential:
    tenant_id: str
    connector_id: str
    values: dict[str, Any]
    date_updated: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "connector_id": self.connector_id,
            "values": self.values,
            "date_updated": self.date_updated,
        }


class ConnectorCredentialStore:
    def __init__(self) -> None:
        self._path = Path(".maia_agent") / "connector_credentials.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self._path.exists():
            self._path.write_text("{}", encoding="utf-8")

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save(self, payload: dict[str, dict[str, Any]]) -> None:
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set(
        self,
        *,
        tenant_id: str,
        connector_id: str,
        values: dict[str, Any],
    ) -> ConnectorCredential:
        key = f"{tenant_id}:{connector_id}"
        row = ConnectorCredential(
            tenant_id=tenant_id,
            connector_id=connector_id,
            values=values,
            date_updated=utc_now().isoformat(),
        )
        with self._lock:
            store = self._load()
            store[key] = row.to_dict()
            self._save(store)
        return row

    def get(self, *, tenant_id: str, connector_id: str) -> ConnectorCredential | None:
        key = f"{tenant_id}:{connector_id}"
        store = self._load()
        row = store.get(key)
        if not row:
            return None
        return ConnectorCredential(
            tenant_id=str(row.get("tenant_id") or tenant_id),
            connector_id=str(row.get("connector_id") or connector_id),
            values=dict(row.get("values") or {}),
            date_updated=str(row.get("date_updated") or ""),
        )

    def list_for_tenant(self, *, tenant_id: str) -> list[ConnectorCredential]:
        prefix = f"{tenant_id}:"
        store = self._load()
        rows: list[ConnectorCredential] = []
        for key, row in store.items():
            if not key.startswith(prefix):
                continue
            rows.append(
                ConnectorCredential(
                    tenant_id=str(row.get("tenant_id") or tenant_id),
                    connector_id=str(row.get("connector_id") or ""),
                    values=dict(row.get("values") or {}),
                    date_updated=str(row.get("date_updated") or ""),
                )
            )
        rows.sort(key=lambda item: item.connector_id)
        return rows

    def delete(self, *, tenant_id: str, connector_id: str) -> bool:
        key = f"{tenant_id}:{connector_id}"
        with self._lock:
            store = self._load()
            if key not in store:
                return False
            del store[key]
            self._save(store)
            return True


_credential_store: ConnectorCredentialStore | None = None


def get_credential_store() -> ConnectorCredentialStore:
    global _credential_store
    if _credential_store is None:
        _credential_store = ConnectorCredentialStore()
    return _credential_store
