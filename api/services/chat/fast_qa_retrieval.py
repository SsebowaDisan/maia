"""Stub — old retrieval replaced by api.services.rag.retrieve."""
import logging
logger = logging.getLogger(__name__)

def load_recent_chunks_for_fast_qa(*args, **kwargs):
    logger.warning("load_recent_chunks_for_fast_qa: deprecated stub")
    return []

def _ranked_chunk_selection(*args, **kwargs):
    return []
