"""External secret provider abstraction.

Config via env:
    MAIA_SECRET_PROVIDER — "internal" (default), "aws", "azure", "vault"

For AWS: AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY (or IAM role)
For Azure: AZURE_VAULT_URL
For HashiCorp Vault: VAULT_ADDR, VAULT_TOKEN
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class SecretProvider(ABC):
    """Uniform interface for secret storage backends."""

    @abstractmethod
    def get(self, key: str, *, tenant_id: str = "") -> str | None: ...

    @abstractmethod
    def set(self, key: str, value: str, *, tenant_id: str = "") -> None: ...

    @abstractmethod
    def delete(self, key: str, *, tenant_id: str = "") -> bool: ...

    @abstractmethod
    def list_keys(self, *, tenant_id: str = "", prefix: str = "") -> list[str]: ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Internal (Fernet vault) provider
# ---------------------------------------------------------------------------

_INTERNAL_CONNECTOR = "__secret_kv__"


class InternalSecretProvider(SecretProvider):
    """Wraps the existing Fernet-based vault for simple key/value secrets."""

    def get(self, key: str, *, tenant_id: str = "") -> str | None:
        from api.services.connectors.vault import get_credential

        data = get_credential(tenant_id or "_global", f"{_INTERNAL_CONNECTOR}/{key}")
        return data.get("value") if data else None

    def set(self, key: str, value: str, *, tenant_id: str = "") -> None:
        from api.services.connectors.vault import store_credential

        store_credential(
            tenant_id or "_global",
            f"{_INTERNAL_CONNECTOR}/{key}",
            {"value": value},
        )

    def delete(self, key: str, *, tenant_id: str = "") -> bool:
        from api.services.connectors.vault import revoke_credential

        return revoke_credential(tenant_id or "_global", f"{_INTERNAL_CONNECTOR}/{key}")

    def list_keys(self, *, tenant_id: str = "", prefix: str = "") -> list[str]:
        from sqlmodel import Session, select

        from api.models.connector_binding import ConnectorBinding
        from ktem.db.engine import engine

        tid = tenant_id or "_global"
        like = f"{_INTERNAL_CONNECTOR}/{prefix}%"
        with Session(engine) as session:
            rows = session.exec(
                select(ConnectorBinding.connector_id)
                .where(ConnectorBinding.tenant_id == tid)
                .where(ConnectorBinding.connector_id.like(like))  # type: ignore[union-attr]
                .where(ConnectorBinding.is_active == True)  # noqa: E712
            ).all()
        strip = f"{_INTERNAL_CONNECTOR}/"
        return [r.removeprefix(strip) for r in rows]

    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "provider": "internal", "detail": "Fernet vault available"}


# ---------------------------------------------------------------------------
# AWS Secrets Manager
# ---------------------------------------------------------------------------


class AwsSecretProvider(SecretProvider):
    """AWS Secrets Manager backend (requires boto3)."""

    def __init__(self) -> None:
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for AWS secret provider. Run: pip install boto3"
            ) from exc
        region = os.getenv("AWS_REGION", "us-east-1")
        self._client = boto3.client("secretsmanager", region_name=region)

    def _path(self, key: str, tenant_id: str) -> str:
        return f"maia/{tenant_id or '_global'}/{key}"

    def get(self, key: str, *, tenant_id: str = "") -> str | None:
        try:
            resp = self._client.get_secret_value(SecretId=self._path(key, tenant_id))
            return resp["SecretString"]
        except self._client.exceptions.ResourceNotFoundException:
            return None

    def set(self, key: str, value: str, *, tenant_id: str = "") -> None:
        path = self._path(key, tenant_id)
        try:
            self._client.update_secret(SecretId=path, SecretString=value)
        except self._client.exceptions.ResourceNotFoundException:
            self._client.create_secret(Name=path, SecretString=value)

    def delete(self, key: str, *, tenant_id: str = "") -> bool:
        try:
            self._client.delete_secret(
                SecretId=self._path(key, tenant_id),
                ForceDeleteWithoutRecovery=False,
            )
            return True
        except self._client.exceptions.ResourceNotFoundException:
            return False

    def list_keys(self, *, tenant_id: str = "", prefix: str = "") -> list[str]:
        path_prefix = f"maia/{tenant_id or '_global'}/{prefix}"
        paginator = self._client.get_paginator("list_secrets")
        keys: list[str] = []
        for page in paginator.paginate(
            Filters=[{"Key": "name", "Values": [path_prefix]}],
        ):
            for entry in page.get("SecretList", []):
                name: str = entry["Name"]
                # Strip the maia/{tenant}/ prefix to return bare key
                parts = name.split("/", 2)
                if len(parts) == 3:
                    keys.append(parts[2])
        return keys

    def health_check(self) -> dict[str, Any]:
        try:
            self._client.list_secrets(MaxResults=1)
            return {"ok": True, "provider": "aws", "detail": "Connected"}
        except Exception as exc:
            return {"ok": False, "provider": "aws", "detail": str(exc)}


# ---------------------------------------------------------------------------
# Azure Key Vault
# ---------------------------------------------------------------------------


class AzureSecretProvider(SecretProvider):
    """Azure Key Vault backend (requires azure-keyvault-secrets + azure-identity)."""

    def __init__(self) -> None:
        try:
            from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]
            from azure.keyvault.secrets import SecretClient  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "azure-keyvault-secrets and azure-identity are required. "
                "Run: pip install azure-keyvault-secrets azure-identity"
            ) from exc
        vault_url = os.environ["AZURE_VAULT_URL"]
        self._client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

    @staticmethod
    def _name(key: str, tenant_id: str) -> str:
        # Azure secret names allow only alphanumerics and dashes
        return f"maia-{(tenant_id or 'global')}-{key}".replace("/", "-").replace("_", "-")

    def get(self, key: str, *, tenant_id: str = "") -> str | None:
        try:
            return self._client.get_secret(self._name(key, tenant_id)).value
        except Exception:
            return None

    def set(self, key: str, value: str, *, tenant_id: str = "") -> None:
        self._client.set_secret(self._name(key, tenant_id), value)

    def delete(self, key: str, *, tenant_id: str = "") -> bool:
        try:
            self._client.begin_delete_secret(self._name(key, tenant_id))
            return True
        except Exception:
            return False

    def list_keys(self, *, tenant_id: str = "", prefix: str = "") -> list[str]:
        name_prefix = f"maia-{(tenant_id or 'global')}-{prefix}"
        return [
            p.name.split("-", 2)[2] if p.name and p.name.count("-") >= 2 else (p.name or "")
            for p in self._client.list_properties_of_secrets()
            if p.name and p.name.startswith(name_prefix)
        ]

    def health_check(self) -> dict[str, Any]:
        try:
            # list with a single iteration to confirm connectivity
            next(iter(self._client.list_properties_of_secrets()), None)
            return {"ok": True, "provider": "azure", "detail": "Connected"}
        except Exception as exc:
            return {"ok": False, "provider": "azure", "detail": str(exc)}


# ---------------------------------------------------------------------------
# HashiCorp Vault (KV v2, stdlib only)
# ---------------------------------------------------------------------------


class HashiCorpVaultProvider(SecretProvider):
    """HashiCorp Vault KV v2 backend using only urllib (no extra deps)."""

    def __init__(self) -> None:
        self._addr = os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200").rstrip("/")
        self._token = os.environ.get("VAULT_TOKEN", "")

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self._addr}/v1/{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-Vault-Token", self._token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {}
            raise

    def _kv_path(self, tenant_id: str, key: str) -> str:
        return f"maia/data/{tenant_id or '_global'}/{key}"

    def get(self, key: str, *, tenant_id: str = "") -> str | None:
        resp = self._request("GET", self._kv_path(tenant_id, key))
        try:
            return resp["data"]["data"]["value"]
        except (KeyError, TypeError):
            return None

    def set(self, key: str, value: str, *, tenant_id: str = "") -> None:
        self._request("POST", self._kv_path(tenant_id, key), {"data": {"value": value}})

    def delete(self, key: str, *, tenant_id: str = "") -> bool:
        path = f"maia/metadata/{tenant_id or '_global'}/{key}"
        try:
            self._request("DELETE", path)
            return True
        except Exception:
            return False

    def list_keys(self, *, tenant_id: str = "", prefix: str = "") -> list[str]:
        path = f"maia/metadata/{tenant_id or '_global'}/"
        try:
            resp = self._request("LIST", path)
            keys: list[str] = resp.get("data", {}).get("keys", [])
            if prefix:
                keys = [k for k in keys if k.startswith(prefix)]
            return keys
        except Exception:
            return []

    def health_check(self) -> dict[str, Any]:
        try:
            url = f"{self._addr}/v1/sys/health"
            req = urllib.request.Request(url, method="GET")
            req.add_header("X-Vault-Token", self._token)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            ok = data.get("initialized", False) and not data.get("sealed", True)
            return {"ok": ok, "provider": "vault", "detail": "Healthy" if ok else "Sealed or uninitialized"}
        except Exception as exc:
            return {"ok": False, "provider": "vault", "detail": str(exc)}


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: SecretProvider | None = None

_PROVIDERS: dict[str, type[SecretProvider]] = {
    "internal": InternalSecretProvider,
    "aws": AwsSecretProvider,
    "azure": AzureSecretProvider,
    "vault": HashiCorpVaultProvider,
}


def get_secret_provider() -> SecretProvider:
    """Return (or create) the singleton SecretProvider based on MAIA_SECRET_PROVIDER env."""
    global _instance
    if _instance is None:
        name = os.getenv("MAIA_SECRET_PROVIDER", "internal").strip().lower()
        cls = _PROVIDERS.get(name)
        if cls is None:
            raise ValueError(
                f"Unknown MAIA_SECRET_PROVIDER={name!r}. "
                f"Valid options: {', '.join(_PROVIDERS)}"
            )
        logger.info("Initialising secret provider: %s", name)
        _instance = cls()
    return _instance
