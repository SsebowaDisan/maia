from fastapi import APIRouter, Depends

from api.auth import get_current_user_id
from api.context import get_context
from api.schemas import SettingsPatchRequest, SettingsResponse
from api.services.settings_service import load_user_settings, save_user_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(user_id: str = Depends(get_current_user_id)):
    context = get_context()
    values = load_user_settings(context=context, user_id=user_id)
    return {"values": values}


@router.patch("", response_model=SettingsResponse)
def patch_settings(
    payload: SettingsPatchRequest,
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    current_values = load_user_settings(context=context, user_id=user_id)
    current_values.update(payload.values)
    saved_values = save_user_settings(
        context=context,
        user_id=user_id,
        values=current_values,
    )
    return {"values": saved_values}

