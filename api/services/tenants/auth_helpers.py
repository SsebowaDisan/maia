"""FastAPI dependency for tenant-aware authentication.

Provides ``get_current_tenant_id`` — a drop-in replacement for the old
``_tenant(user_id)`` pattern used across routers.  Instead of blindly
returning the user_id, it resolves the *real* tenant via the resolver.

Usage in a router::

    from api.services.tenants.auth_helpers import get_current_tenant_id

    @router.get("/things")
    def list_things(tenant_id: Annotated[str, Depends(get_current_tenant_id)]):
        ...
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from api.auth import get_current_user
from api.models.user import User
from api.services.tenants.resolver import resolve_tenant_id


def get_current_tenant_id(
    user: Annotated[User, Depends(get_current_user)],
) -> str:
    """Resolve and return the authenticated user's tenant_id."""
    return resolve_tenant_id(user)
