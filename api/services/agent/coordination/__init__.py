"""Multi-agent coordination primitives (Innovation #9).

Exports:
    ConsensusEngine  — multi-agent consensus with proposal gathering and arbitration
    GoalDecomposer   — hierarchical goal decomposition across agents
    SharedStateBus   — inter-agent shared state for a single run
"""
from api.services.agent.coordination.consensus import (
    AgentProposal,
    ConsensusEngine,
    ConsensusResult,
)
from api.services.agent.coordination.hierarchical_goals import (
    GoalDecomposer,
    GoalNode,
    GoalTree,
)
from api.services.agent.coordination.shared_state import SharedStateBus

__all__ = [
    "AgentProposal",
    "ConsensusEngine",
    "ConsensusResult",
    "GoalDecomposer",
    "GoalNode",
    "GoalTree",
    "SharedStateBus",
]
