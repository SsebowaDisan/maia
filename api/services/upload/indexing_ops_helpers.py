"""Stub — old indexing ops replaced by api.services.rag.pipeline.

Kept as shim for api.services.ingestion.manager_api_helpers imports.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def persist_source_record(*args, **kwargs) -> Any:
    logger.warning("persist_source_record: deprecated stub called")
    return None


def persist_index_record(*args, **kwargs) -> Any:
    logger.warning("persist_index_record: deprecated stub called")
    return None


def update_source_status(*args, **kwargs) -> None:
    logger.warning("update_source_status: deprecated stub called")


def delete_source_records(*args, **kwargs) -> int:
    logger.warning("delete_source_records: deprecated stub called")
    return 0
