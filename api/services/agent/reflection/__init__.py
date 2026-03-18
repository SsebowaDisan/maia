"""Reflection package — advanced self-reflection for the Maia agent.

Public surface
--------------
ConfidenceScorer  — scores claims and full responses with calibrated confidence
SelfRepairEngine  — diagnoses verification failures and generates repair plans
StrategyDetector  — detects stuck agents and suggests strategy pivots
"""
from .confidence_scorer import ConfidenceScorer
from .self_repair import SelfRepairEngine
from .strategy_detector import StrategyDetector

__all__ = [
    "ConfidenceScorer",
    "SelfRepairEngine",
    "StrategyDetector",
]
