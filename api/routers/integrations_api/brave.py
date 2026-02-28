from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user_id
from api.services.search.brave_search import BraveSearchService
from api.services.search.errors import BraveSearchError

from .common import (
    BRAVE_CONNECTOR_ID,
    publish_event,
    resolve_brave_env_key,
    stored_secret,
    tenant_settings,
)
from .schemas import WebSearchRequest

router = APIRouter(tags=["agent-integrations"])


@router.get("/integrations/brave/status")
def brave_integration_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = tenant_settings(user_id)
    env_key = resolve_brave_env_key()
    stored_key = stored_secret(tenant_id, BRAVE_CONNECTOR_ID, "BRAVE_SEARCH_API_KEY")
    source: str | None = None
    if env_key:
        source = "env"
    elif stored_key:
        source = "stored"
    return {
        "configured": bool(source),
        "source": source,
    }


@router.post("/tools/web_search")
def run_web_search(
    payload: WebSearchRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = tenant_settings(user_id)
    key = resolve_brave_env_key() or stored_secret(tenant_id, BRAVE_CONNECTOR_ID, "BRAVE_SEARCH_API_KEY")
    if not key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "brave_api_key_missing",
                "message": "BRAVE_SEARCH_API_KEY is not configured.",
            },
        )

    run_id = str(payload.run_id or "").strip() or None
    query = " ".join(str(payload.query or "").split())
    publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="status",
        message="Searching web...",
        data={"provider": "brave"},
    )
    publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="brave.search.query",
        message="Running Brave search query",
        data={"query": query, "domain": payload.domain or None},
    )

    try:
        service = BraveSearchService(api_key=key)
        if payload.domain:
            result = service.site_search(
                domain=payload.domain,
                query=query,
                count=payload.count,
                offset=payload.offset,
                country=payload.country,
                safesearch=payload.safesearch,
            )
        else:
            result = service.web_search(
                query=query,
                count=payload.count,
                offset=payload.offset,
                country=payload.country,
                safesearch=payload.safesearch,
            )
    except BraveSearchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "brave_search_failed",
                "message": "Brave search request failed.",
                "details": {"error": str(exc)},
            },
        ) from exc

    rows = result.get("results")
    results = rows if isinstance(rows, list) else []
    top_urls = [str(item.get("url") or "") for item in results if isinstance(item, dict)][:5]
    publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="brave.search.results",
        message=f"Brave search returned {len(results)} result(s)",
        data={"top_urls": top_urls},
    )
    return result
