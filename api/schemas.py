from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.message_blocks import CanvasDocumentRecord, MessageBlock


class HaltReason(str, Enum):
    """Named halt/fallback conditions surfaced in the response contract.

    String enum so values survive JSON serialisation without conversion.
    """
    no_snippets = "no_snippets"
    no_relevant_snippets = "no_relevant_snippets"
    llm_timeout = "llm_timeout"
    context_too_large = "context_too_large"
    tool_failure = "tool_failure"
    mode_downgraded = "mode_downgraded"
    user_cancelled = "user_cancelled"
    llm_quota_exceeded = "llm_quota_exceeded"


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
    icon_key: str | None = None
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
    scope: str | None = None
    rag_ready: bool | None = None
    citation_ready: bool | None = None
    citation_status: str | None = None
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


class MindmapFocusSchema(BaseModel):
    """Typed contract for mindmap focus requests.

    All fields are optional strings; omitted / null / empty values are treated
    as "no constraint" for that dimension.

    Filtering priority (highest to lowest):
      1. node_id  — exact node-id match in a previous mindmap payload (deterministic)
      2. source_id — exact source UUID match
      3. source_name — case-insensitive substring match on source name
      4. page_ref — exact page-label / page-reference match
      5. unit_id  — exact unit/section ID match
      6. text     — token-overlap ranking over the remaining candidates
    """

    model_config = ConfigDict(extra="ignore")

    node_id: str = ""
    source_id: str = ""
    source_name: str = ""
    page_ref: str = ""
    unit_id: str = ""
    text: str = ""

    @field_validator("node_id", "source_id", "source_name", "page_ref", "unit_id", "text", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str:
        return " ".join(str(v or "").split()).strip()

    @model_validator(mode="before")
    @classmethod
    def _accept_none(cls, v: Any) -> Any:
        # Allow None to produce an empty focus object instead of a validation error
        if v is None:
            return {}
        return v

    def is_empty(self) -> bool:
        return not any([
            self.node_id, self.source_id, self.source_name,
            self.page_ref, self.unit_id, self.text,
        ])


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
    mindmap_focus: MindmapFocusSchema = Field(default_factory=MindmapFocusSchema)
    mindmap_settings: dict[str, Any] = Field(default_factory=dict)
    agent_mode: Literal["ask", "rag", "company_agent", "deep_search", "brain"] = "ask"
    agent_goal: str | None = None
    access_mode: Literal["restricted", "full_access"] | None = None
    agent_id: str | None = None  # explicit agent selection — skips intent resolution


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
    blocks: list[MessageBlock] = Field(default_factory=list)
    documents: list[CanvasDocumentRecord] = Field(default_factory=list)
    info: str
    plot: dict[str, Any] | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["ask", "company_agent", "deep_search", "brain"] = "ask"
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
    halt_reason: str | None = None
    mode_actually_used: str | None = None
