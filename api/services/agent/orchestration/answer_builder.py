"""Compatibility shim for answer builder composition.

Deprecated module path for implementation details:
- use `api.services.agent.orchestration.answer_builder_sections` for new code.
"""

from .answer_builder_sections import compose_professional_answer

__all__ = ["compose_professional_answer"]
