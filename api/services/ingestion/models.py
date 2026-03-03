from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, SQLModel

from .config import JOB_STATUS_QUEUED


class IngestionJob(SQLModel, table=True):
    __tablename__ = "maia_ingestion_job"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True, index=True)
    user_id: str = Field(index=True)
    kind: str = Field(index=True)  # files | urls
    status: str = Field(default=JOB_STATUS_QUEUED, index=True)
    index_id: int | None = Field(default=None, index=True)
    reindex: bool = Field(default=True)
    total_items: int = Field(default=0)
    processed_items: int = Field(default=0)
    success_count: int = Field(default=0)
    failure_count: int = Field(default=0)
    bytes_total: int = Field(default=0)
    bytes_persisted: int = Field(default=0)
    bytes_indexed: int = Field(default=0)

    # payload stores source descriptors:
    # files -> [{"name": "...", "path": "...", "size": 123}]
    # urls  -> {"urls": [...], "web_crawl_depth": 0, ...}
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(SAJSON))
    items: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(SAJSON))
    errors: list[str] = Field(default_factory=list, sa_column=Column(SAJSON))
    file_ids: list[str] = Field(default_factory=list, sa_column=Column(SAJSON))
    debug: list[str] = Field(default_factory=list, sa_column=Column(SAJSON))

    message: str = Field(default="")
    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_updated: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_started: datetime | None = Field(default=None)
    date_finished: datetime | None = Field(default=None)
