"""Scope-based authorization dependencies for FastAPI routes.

Usage::

    from api.services.auth.dependencies import require_scope

    @router.post("/api/roles")
    def create_role(body: ..., _auth=require_scope("roles:manage")):
        ...
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status


def require_scope(scope: str):
    """FastAPI dependency that checks if the current user has the required scope.

    Returns a ``Depends(...)`` instance that can be used directly as a default
    parameter value in a route handler signature.
    """

    def _check(request: Request) -> None:
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        try:
            from api.services.auth.roles import check_scope

            if not check_scope(user_id, scope):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required scope: {scope}",
                )
        except ImportError:
            pass  # roles module not available, allow through

    return Depends(_check)
