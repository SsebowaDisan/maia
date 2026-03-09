from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.services.ollama import DEFAULT_OLLAMA_BASE_URL


class MapsSaveRequest(BaseModel):
    api_key: str = Field(min_length=16, max_length=512)


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    count: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=200)
    country: str = Field(default="BE", min_length=2, max_length=2)
    safesearch: str = Field(default="moderate", min_length=2, max_length=20)
    domain: str | None = Field(default=None, max_length=255)
    run_id: str | None = Field(default=None, max_length=120)


class OllamaConfigRequest(BaseModel):
    base_url: str = Field(default=DEFAULT_OLLAMA_BASE_URL, min_length=8, max_length=256)


class OllamaPullRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=8, max_length=256)
    auto_select: bool = True
    run_id: str | None = Field(default=None, max_length=120)


class OllamaSelectRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=8, max_length=256)
    run_id: str | None = Field(default=None, max_length=120)


class OllamaEmbeddingSelectRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=8, max_length=256)
    run_id: str | None = Field(default=None, max_length=120)


class OllamaStartRequest(BaseModel):
    base_url: str | None = Field(default=None, min_length=8, max_length=256)
    wait_seconds: int = Field(default=10, ge=2, le=30)
    auto_install: bool = True
    run_id: str | None = Field(default=None, max_length=120)


class OllamaEmbeddingApplyAllRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=8, max_length=256)
    run_id: str | None = Field(default=None, max_length=120)


class GoogleWorkspaceAuthModeRequest(BaseModel):
    mode: Literal["oauth", "service_account"] = "oauth"


class GoogleOAuthServicesRequest(BaseModel):
    services: list[str] = Field(default_factory=list, max_length=20)


class GoogleWorkspaceLinkAnalyzeRequest(BaseModel):
    link: str = Field(min_length=4, max_length=2048)


class GoogleWorkspaceLinkCheckRequest(BaseModel):
    link: str = Field(min_length=4, max_length=2048)
    action: Literal["read", "edit"] = "read"


class GoogleWorkspaceLinkAliasSaveRequest(BaseModel):
    alias: str = Field(min_length=2, max_length=120)
    link: str = Field(min_length=4, max_length=2048)
