from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlaybookCreateRequest(BaseModel):
    name: str
    prompt_template: str
    tool_ids: list[str] = Field(default_factory=list)


class PlaybookPatchRequest(BaseModel):
    name: str | None = None
    prompt_template: str | None = None
    tool_ids: list[str] | None = None


class CredentialUpsertRequest(BaseModel):
    connector_id: str
    values: dict[str, Any] = Field(default_factory=dict)


class ScheduleCreateRequest(BaseModel):
    name: str
    prompt: str
    frequency: str = Field(default="weekly")
    outputs: list[str] = Field(default_factory=lambda: ["markdown"])
    channels: list[str] = Field(default_factory=list)


class ScheduleToggleRequest(BaseModel):
    enabled: bool


class GovernancePatchRequest(BaseModel):
    global_kill_switch: bool | None = None
    tool_id: str | None = None
    tool_enabled: bool | None = None


class GoogleOAuthExchangeRequest(BaseModel):
    code: str
    redirect_uri: str | None = None
    state: str | None = None
    connector_ids: list[str] = Field(
        default_factory=lambda: [
            "google_workspace",
            "gmail",
            "google_calendar",
            "google_analytics",
            "google_ads",
        ]
    )


class GoogleOAuthConfigSaveRequest(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str | None = None


class GoogleOAuthSetupRequestCreateRequest(BaseModel):
    note: str | None = None


GOOGLE_OAUTH_CONNECTOR_IDS = [
    "google_workspace",
    "gmail",
    "google_calendar",
    "google_analytics",
    "google_ads",
]
