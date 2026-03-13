from fastapi import APIRouter, Depends

from api.auth import get_current_user_id
from api.context import get_context
from api.schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationSummary,
    ConversationUpdateRequest,
    MindmapShareCreateRequest,
    MindmapShareResponse,
)
from api.services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
def list_conversations(user_id: str = Depends(get_current_user_id)):
    return conversation_service.list_conversations(user_id=user_id)


@router.post("", response_model=ConversationDetail)
def create_conversation(
    payload: ConversationCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    _ = get_context()
    return conversation_service.create_conversation(
        user_id=user_id,
        name=payload.name,
        is_public=payload.is_public,
    )


@router.get("/mindmaps/shared/{share_id}", response_model=MindmapShareResponse)
def get_shared_mindmap(share_id: str):
    return conversation_service.get_mindmap_share(share_id=share_id)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    return conversation_service.get_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
    )


@router.patch("/{conversation_id}", response_model=ConversationDetail)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    return conversation_service.update_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        name=payload.name,
        is_public=payload.is_public,
    )


@router.post(
    "/{conversation_id}/mindmaps/share",
    response_model=MindmapShareResponse,
)
def create_mindmap_share(
    conversation_id: str,
    payload: MindmapShareCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    return conversation_service.create_mindmap_share(
        user_id=user_id,
        conversation_id=conversation_id,
        mindmap=payload.map,
        title=payload.title,
    )


@router.get("/{conversation_id}/analytics")
def get_conversation_analytics(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from api.services.conversation_analytics import build_analytics_response

    conv = conversation_service.get_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
    )
    return build_analytics_response(conversation_id, conv.get("data_source") or {})


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    conversation_service.delete_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
    )
    return {"status": "deleted"}
