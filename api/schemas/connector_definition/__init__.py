"""Connector definition schema package."""
from .auth_config import (
    ApiKeyAuthConfig,
    AuthConfig,
    AuthStrategy,
    BasicAuthConfig,
    BearerAuthConfig,
    CustomAuthConfig,
    NoAuthConfig,
    OAuth2AuthConfig,
)
from .schema import (
    ConnectorAuthKind,
    ConnectorCategory,
    ConnectorDefinitionSchema,
    ConnectorSceneFamily,
    ConnectorSetupMode,
    ConnectorSetupStatus,
    ConnectorSubService,
    ConnectorVisibility,
)
from .tool_schema import (
    ToolActionClass,
    ToolParameter,
    ToolParameterType,
    ToolSchema,
)

__all__ = [
    "ApiKeyAuthConfig",
    "AuthConfig",
    "AuthStrategy",
    "BasicAuthConfig",
    "BearerAuthConfig",
    "ConnectorAuthKind",
    "ConnectorCategory",
    "ConnectorDefinitionSchema",
    "ConnectorSceneFamily",
    "ConnectorSetupMode",
    "ConnectorSetupStatus",
    "ConnectorSubService",
    "ConnectorVisibility",
    "CustomAuthConfig",
    "NoAuthConfig",
    "OAuth2AuthConfig",
    "ToolActionClass",
    "ToolParameter",
    "ToolParameterType",
    "ToolSchema",
]
