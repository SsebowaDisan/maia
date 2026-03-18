"""Agent Memory package — legacy service + advanced memory subsystems.

Re-exports the original AgentMemoryService / get_memory_service so that
existing ``from api.services.agent.memory import get_memory_service``
imports continue to work without changes.

Also exports the three new advanced-memory components:
  - SemanticMemoryStore  (TF-IDF episodic memory)
  - TraceLearner         (automated trace learning)
  - ToolPatternDB        (tool failure pattern database)
"""
from __future__ import annotations

# ---- Legacy memory service (moved from memory.py into this package) --------
from api.services.agent.memory._service import (  # noqa: F401
    AgentMemoryService,
    JsonStore,
    get_memory_service,
)

# ---- Advanced memory subsystems -------------------------------------------
from api.services.agent.memory.semantic_memory import (  # noqa: F401
    AgentEpisode,
    SemanticMemoryStore,
)
from api.services.agent.memory.trace_learner import (  # noqa: F401
    LearnedRule,
    TraceLearner,
)
from api.services.agent.memory.tool_patterns import (  # noqa: F401
    ToolOutcomeRecord,
    ToolPatternDB,
    get_tool_pattern_db,
    hash_params,
)

__all__ = [
    # Legacy
    "AgentMemoryService",
    "JsonStore",
    "get_memory_service",
    # Semantic memory
    "AgentEpisode",
    "SemanticMemoryStore",
    # Trace learning
    "LearnedRule",
    "TraceLearner",
    # Tool patterns
    "ToolOutcomeRecord",
    "ToolPatternDB",
    "get_tool_pattern_db",
    "hash_params",
]
