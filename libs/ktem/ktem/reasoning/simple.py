"""Compatibility shim for simple reasoning pipelines.

Deprecated module path for implementation details:
- use `ktem.reasoning.simple_reasoning` for new code.
"""

from .simple_reasoning import AddQueryContextPipeline, FullDecomposeQAPipeline, FullQAPipeline

__all__ = [
    "AddQueryContextPipeline",
    "FullDecomposeQAPipeline",
    "FullQAPipeline",
]
