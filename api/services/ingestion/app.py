from __future__ import annotations

from .manager import IngestionJobManager

_ingestion_manager = IngestionJobManager()


def get_ingestion_manager() -> IngestionJobManager:
    return _ingestion_manager
