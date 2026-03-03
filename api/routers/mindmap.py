from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from api.auth import get_current_user_id
from api.context import get_context
from api.services import mindmap_service

router = APIRouter(prefix="/api/mindmap", tags=["mindmap"])


@router.get("")
def get_mindmap(
    source_id: str = Query(..., alias="sourceId"),
    map_type: str = Query("structure", alias="mapType"),
    max_depth: int = Query(4, alias="maxDepth"),
    include_reasoning_map: bool = Query(True, alias="includeReasoningMap"),
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    return mindmap_service.build_source_mindmap(
        context=context,
        user_id=user_id,
        source_id=source_id,
        map_type=map_type,
        max_depth=max_depth,
        include_reasoning_map=include_reasoning_map,
    )


@router.get("/export/json")
def export_mindmap_json(
    source_id: str = Query(..., alias="sourceId"),
    map_type: str = Query("structure", alias="mapType"),
    max_depth: int = Query(4, alias="maxDepth"),
    include_reasoning_map: bool = Query(True, alias="includeReasoningMap"),
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    return mindmap_service.build_source_mindmap(
        context=context,
        user_id=user_id,
        source_id=source_id,
        map_type=map_type,
        max_depth=max_depth,
        include_reasoning_map=include_reasoning_map,
    )


@router.get("/export/markdown", response_class=PlainTextResponse)
def export_mindmap_markdown(
    source_id: str = Query(..., alias="sourceId"),
    map_type: str = Query("structure", alias="mapType"),
    max_depth: int = Query(4, alias="maxDepth"),
    include_reasoning_map: bool = Query(True, alias="includeReasoningMap"),
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    payload = mindmap_service.build_source_mindmap(
        context=context,
        user_id=user_id,
        source_id=source_id,
        map_type=map_type,
        max_depth=max_depth,
        include_reasoning_map=include_reasoning_map,
    )
    return mindmap_service.to_markdown(payload)
