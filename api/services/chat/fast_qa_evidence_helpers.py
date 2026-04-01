"""Stub — old evidence helpers replaced by api.services.rag.

All functions return safe defaults so fast_qa.py doesn't crash.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

def annotate_primary_sources(*args, **kwargs):
    return args[0] if args else []

def apply_mindmap_focus(*args, **kwargs):
    return args[0] if args else []

def assess_evidence_sufficiency_with_llm(*args, **kwargs):
    return {"sufficient": False, "reason": "deprecated stub"}

def build_no_relevant_evidence_answer(*args, **kwargs):
    return "I couldn't find relevant information in the selected sources."

def finalize_retrieved_snippets(*args, **kwargs):
    return args[0] if args else []

def normalize_outline(*args, **kwargs):
    return {}

def plan_adaptive_outline(*args, **kwargs):
    return {}

def prioritize_primary_evidence(*args, **kwargs):
    return args[0] if args else []

def selected_source_ids(*args, **kwargs):
    return []

def select_relevant_snippets_with_llm(*args, **kwargs):
    return args[0] if args else []

def snippet_score(*args, **kwargs):
    return 0.0

def expand_retrieval_query_for_gap(*args, **kwargs):
    return args[0] if args else ""
