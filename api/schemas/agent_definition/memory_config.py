"""MemoryConfig — defines how an agent stores and retrieves memories.

Responsibility: single pydantic schema for agent memory configuration.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class MemoryBackend(str, Enum):
    """Storage backend for each memory tier."""

    none = "none"
    redis = "redis"
    vector = "vector"
    postgres = "postgres"


class WorkingMemoryConfig(BaseModel):
    """Per-conversation short-term memory (cleared when conversation ends)."""

    enabled: bool = True
    backend: MemoryBackend = MemoryBackend.redis
    ttl_seconds: Annotated[int, Field(ge=60, le=86400)] = 3600
    max_tokens: Annotated[int, Field(ge=256, le=32768)] = 8192


class EpisodicMemoryConfig(BaseModel):
    """Per-agent execution history — searchable across conversations."""

    enabled: bool = False
    backend: MemoryBackend = MemoryBackend.vector
    max_episodes: Annotated[int, Field(ge=1, le=10000)] = 500
    similarity_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.75
    top_k_retrieval: Annotated[int, Field(ge=1, le=50)] = 5


class SemanticMemoryConfig(BaseModel):
    """Wraps the tenant RAG index — read-only knowledge retrieval."""

    enabled: bool = True
    index_ids: list[int] = Field(default_factory=list)
    top_k_retrieval: Annotated[int, Field(ge=1, le=100)] = 10


class MemoryConfig(BaseModel):
    """Aggregated memory configuration for an agent definition."""

    working: WorkingMemoryConfig = Field(default_factory=WorkingMemoryConfig)
    episodic: EpisodicMemoryConfig = Field(default_factory=EpisodicMemoryConfig)
    semantic: SemanticMemoryConfig = Field(default_factory=SemanticMemoryConfig)
