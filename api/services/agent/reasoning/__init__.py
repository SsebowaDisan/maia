"""Reasoning package — advanced tool selection and reasoning capabilities.

Public surface
--------------
ProspectiveReasoner  — estimates step success before committing (Innovation #1)
StepForecast         — forecast result from prospective reasoning

ChainOfThoughtReasoner — explicit chain-of-thought before tool calls
ReasoningChain         — structured reasoning chain output
RecoveryReasoning      — structured failure analysis output

ToolComposer     — automatic tool composition for complex operations (Innovation #9)
CompositionPlan  — planned tool chain

TreeOfThoughtPlanner — multi-candidate plan generation and selection (Innovation #6)
PlanCandidate        — a single plan option

CausalDAG      — dependency graph from steps with conflict detection (Innovation #4)
CausalGraph    — the assembled DAG
CausalNode     — a node in the DAG
CausalEdge     — an edge in the DAG

KnowledgeGraphBuilder — entity/relationship graph from evidence (Innovation #5)
KnowledgeGraph        — the assembled knowledge graph
Entity                — a named entity
Relationship          — a directed relationship
Insight               — a non-obvious pattern

HypothesisTracker — multi-hypothesis tracking with Bayesian updates (Innovation #2)
Hypothesis        — a single tracked hypothesis
"""
from .prospective import ProspectiveReasoner, StepForecast
from .chain_of_thought import ChainOfThoughtReasoner, ReasoningChain, RecoveryReasoning
from .tool_composer import ToolComposer, CompositionPlan
from .tree_of_thought import TreeOfThoughtPlanner, PlanCandidate
from .causal_dag import CausalDAG, CausalGraph, CausalNode, CausalEdge
from .knowledge_graph import KnowledgeGraphBuilder, KnowledgeGraph, Entity, Relationship, Insight
from .hypothesis_tracker import HypothesisTracker, Hypothesis

__all__ = [
    "CausalDAG",
    "CausalEdge",
    "CausalGraph",
    "CausalNode",
    "ChainOfThoughtReasoner",
    "CompositionPlan",
    "Entity",
    "Hypothesis",
    "HypothesisTracker",
    "Insight",
    "KnowledgeGraph",
    "KnowledgeGraphBuilder",
    "PlanCandidate",
    "ProspectiveReasoner",
    "ReasoningChain",
    "RecoveryReasoning",
    "Relationship",
    "StepForecast",
    "ToolComposer",
    "TreeOfThoughtPlanner",
]
