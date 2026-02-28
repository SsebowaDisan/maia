"""Compatibility shim for execution step loop orchestration.

Deprecated module path for implementation details:
- use `api.services.agent.orchestration.step_execution_sections` for new code.
"""

from .step_execution_sections import execute_planned_steps

__all__ = ["execute_planned_steps"]
