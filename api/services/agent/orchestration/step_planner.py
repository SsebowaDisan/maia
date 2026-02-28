"""Compatibility shim for execution step planning.

Deprecated module path for implementation details:
- use `api.services.agent.orchestration.step_planner_sections` for new code.
"""

from .step_planner_sections import build_execution_steps

__all__ = ["build_execution_steps"]
