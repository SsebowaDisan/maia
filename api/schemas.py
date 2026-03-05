from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class ConversationCreateRequest(BaseModel):
    name: str | None = None
    is_public: bool = False


class ConversationUpdateRequest(BaseModel):
    name: str | None = None
    is_public: bool | None = None


class ConversationSummary(BaseModel):
    id: str
    name: str
    user: str
    is_public: bool
    date_created: datetime
    date_updated: datetime
    message_count: int


class ConversationDetail(ConversationSummary):
    data_source: dict[str, Any] = Field(default_factory=dict)


class MindmapShareCreateRequest(BaseModel):
    map: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None


class MindmapShareResponse(BaseModel):
    share_id: str
    conversation_id: str
    title: str
    date_created: datetime
    map: dict[str, Any] = Field(default_factory=dict)


class SettingsResponse(BaseModel):
    values: dict[str, Any]


class SettingsPatchRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class UploadItem(BaseModel):
    file_name: str
    status: str
    message: str | None = None
    file_id: str | None = None


class UploadResponse(BaseModel):
    index_id: int
    file_ids: list[str]
    errors: list[str]
    items: list[UploadItem]
    debug: list[str]


class IngestionJobResponse(BaseModel):
    id: str
    user_id: str
    kind: str
    status: str
    index_id: int | None = None
    reindex: bool
    total_items: int
    processed_items: int
    success_count: int
    failure_count: int
    bytes_total: int = 0
    bytes_persisted: int = 0
    bytes_indexed: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    file_ids: list[str] = Field(default_factory=list)
    debug: list[str] = Field(default_factory=list)
    message: str = ""
    date_created: str | None = None
    date_updated: str | None = None
    date_started: str | None = None
    date_finished: str | None = None


class UploadUrlsRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)
    index_id: int | None = None
    reindex: bool = False
    web_crawl_depth: int = 0
    web_crawl_max_pages: int = 0
    web_crawl_same_domain_only: bool = True
    include_pdfs: bool = True
    include_images: bool = True


class FileRecord(BaseModel):
    id: str
    name: str
    size: int
    note: dict[str, Any]
    date_created: datetime


class FileListResponse(BaseModel):
    index_id: int
    files: list[FileRecord]


class FileActionResult(BaseModel):
    file_id: str
    status: str
    message: str | None = None


class BulkDeleteFilesRequest(BaseModel):
    file_ids: list[str] = Field(default_factory=list)
    index_id: int | None = None


class BulkDeleteFilesResponse(BaseModel):
    index_id: int
    deleted_ids: list[str] = Field(default_factory=list)
    failed: list[FileActionResult] = Field(default_factory=list)


class BulkDeleteUrlsRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)
    index_id: int | None = None


class UrlActionResult(BaseModel):
    url: str
    status: str
    message: str | None = None


class BulkDeleteUrlsResponse(BaseModel):
    index_id: int
    deleted_ids: list[str] = Field(default_factory=list)
    deleted_urls: list[str] = Field(default_factory=list)
    failed: list[UrlActionResult] = Field(default_factory=list)


class FileGroupRecord(BaseModel):
    id: str
    name: str
    file_ids: list[str] = Field(default_factory=list)
    date_created: datetime


class FileGroupListResponse(BaseModel):
    index_id: int
    groups: list[FileGroupRecord] = Field(default_factory=list)


class FileGroupResponse(BaseModel):
    index_id: int
    group: FileGroupRecord


class CreateFileGroupRequest(BaseModel):
    name: str
    file_ids: list[str] = Field(default_factory=list)
    index_id: int | None = None


class RenameFileGroupRequest(BaseModel):
    name: str
    index_id: int | None = None


class MoveFilesToGroupRequest(BaseModel):
    file_ids: list[str] = Field(default_factory=list)
    group_id: str | None = None
    group_name: str | None = None
    mode: Literal["append", "replace"] = "append"
    index_id: int | None = None


class MoveFilesToGroupResponse(BaseModel):
    index_id: int
    group: FileGroupRecord
    moved_ids: list[str] = Field(default_factory=list)
    skipped_ids: list[str] = Field(default_factory=list)


class DeleteFileGroupResponse(BaseModel):
    index_id: int
    group_id: str
    status: str = "deleted"


class IndexSelection(BaseModel):
    mode: Literal["all", "select", "disabled"] = "all"
    file_ids: list[str] = Field(default_factory=list)


class ChatAttachmentRecord(BaseModel):
    name: str = ""
    file_id: str | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    index_selection: dict[str, IndexSelection] = Field(default_factory=dict)
    attachments: list[ChatAttachmentRecord] = Field(default_factory=list)
    reasoning_type: str | None = None
    llm: str | None = None
    use_mindmap: bool | None = None
    citation: str | None = None
    language: str | None = None
    command: str | None = None
    setting_overrides: dict[str, Any] = Field(default_factory=dict)
    mindmap_focus: dict[str, Any] = Field(default_factory=dict)
    mindmap_settings: dict[str, Any] = Field(default_factory=dict)
    agent_mode: Literal["ask", "company_agent"] = "ask"
    agent_goal: str | None = None
    access_mode: Literal["restricted", "full_access"] | None = None


class AgentActionRecord(BaseModel):
    tool_id: str
    action_class: Literal["read", "draft", "execute"]
    status: Literal["success", "failed", "skipped"]
    summary: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSourceRecord(BaseModel):
    source_type: str
    label: str
    url: str | None = None
    file_id: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceUsageRecord(BaseModel):
    source_id: str = ""
    source_name: str = "Indexed file"
    source_type: str = "file"
    retrieved_count: int = 0
    cited_count: int = 0
    max_strength_score: float = 0.0
    avg_strength_score: float = 0.0
    citation_share: float = 0.0


class ChatResponse(BaseModel):
    conversation_id: str
    conversation_name: str
    message: str
    answer: str
    info: str
    plot: dict[str, Any] | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["ask", "company_agent"] = "ask"
    actions_taken: list[AgentActionRecord] = Field(default_factory=list)
    sources_used: list[AgentSourceRecord] = Field(default_factory=list)
    source_usage: list[SourceUsageRecord] = Field(default_factory=list)
    next_recommended_steps: list[str] = Field(default_factory=list)
    needs_human_review: bool = False
    human_review_notes: str | None = None
    web_summary: dict[str, Any] = Field(default_factory=dict)
    info_panel: dict[str, Any] = Field(default_factory=dict)
    activity_run_id: str | None = None
    mindmap: dict[str, Any] = Field(default_factory=dict)
