"""AuthConfig — authentication strategies for connectors.

Responsibility: single pydantic schema for connector authentication configuration.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Union

from pydantic import BaseModel, Field


class AuthStrategy(str, Enum):
    none = "none"
    api_key = "api_key"
    oauth2 = "oauth2"
    basic = "basic"
    bearer = "bearer"
    custom = "custom"


class NoAuthConfig(BaseModel):
    strategy: Literal[AuthStrategy.none] = AuthStrategy.none


class ApiKeyAuthConfig(BaseModel):
    strategy: Literal[AuthStrategy.api_key] = AuthStrategy.api_key

    # Where the key is sent: "header" | "query" | "cookie"
    placement: str = "header"

    # Header / query param name, e.g. "X-API-Key" or "api_key".
    param_name: str = "X-API-Key"

    # Human-readable label shown in the credential setup UI.
    credential_label: str = "API Key"

    # Optional prefix prepended to the key value, e.g. "Bearer ".
    value_prefix: str = ""


class OAuth2AuthConfig(BaseModel):
    strategy: Literal[AuthStrategy.oauth2] = AuthStrategy.oauth2

    # Standard OAuth2 endpoints.
    authorization_url: str
    token_url: str
    revoke_url: str | None = None

    # OAuth2 scopes required by this connector.
    scopes: list[str] = Field(default_factory=list)

    # If True, the platform uses the PKCE flow (recommended for public clients).
    use_pkce: bool = True

    # Where to store tenant tokens after the exchange.
    # "binding" = encrypted in ConnectorBinding (default)
    token_storage: str = "binding"


class BasicAuthConfig(BaseModel):
    strategy: Literal[AuthStrategy.basic] = AuthStrategy.basic

    username_label: str = "Username"
    password_label: str = "Password"


class BearerAuthConfig(BaseModel):
    strategy: Literal[AuthStrategy.bearer] = AuthStrategy.bearer

    credential_label: str = "Bearer Token"
    # Optional: token URL to exchange client_credentials for a bearer token.
    token_url: str | None = None


class CustomAuthConfig(BaseModel):
    strategy: Literal[AuthStrategy.custom] = AuthStrategy.custom

    # Free-form credential field names shown in the setup UI.
    credential_fields: list[str] = Field(default_factory=list)

    # Instructions rendered in the credential setup wizard.
    setup_instructions: str = ""


AuthConfig = Union[
    NoAuthConfig,
    ApiKeyAuthConfig,
    OAuth2AuthConfig,
    BasicAuthConfig,
    BearerAuthConfig,
    CustomAuthConfig,
]
