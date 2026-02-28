"""Compatibility shim for agent intelligence helpers.

Deprecated module path for implementation details:
- use `api.services.agent.intelligence_sections` for new code.
"""

from .intelligence_sections import TaskIntelligence, build_verification_report, derive_task_intelligence

__all__ = ["TaskIntelligence", "derive_task_intelligence", "build_verification_report"]
