"""Unified schema exports for legacy + Agent OS contracts.

This package shadows the legacy ``api/schemas.py`` module path. A large part of
the codebase still imports from ``api.schemas`` (for example ``ChatRequest``).
To keep those imports stable while adding package-based schemas, this module:

1. Re-exports all legacy symbols from ``api/schemas.py``.
2. Re-exports new package schemas from ``workflow_definition``.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any
import sys

from .workflow_definition import WorkflowDefinitionSchema, WorkflowEdge, WorkflowStep


def _load_legacy_schema_module() -> ModuleType | None:
    legacy_path = Path(__file__).resolve().parent.parent / "schemas.py"
    spec = spec_from_file_location("api._legacy_schemas", legacy_path)
    if spec is None or spec.loader is None:
        return None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        # Remove the broken partial module so future imports don't silently
        # receive an incomplete object.
        sys.modules.pop(spec.name, None)
        return None
    return module


_legacy_module = _load_legacy_schema_module()
_legacy_exports: dict[str, Any] = {}
if _legacy_module is not None:
    _legacy_exports = {
        name: getattr(_legacy_module, name)
        for name in dir(_legacy_module)
        if not name.startswith("_")
    }
    globals().update(_legacy_exports)

    # Rebuild Pydantic models that use `from __future__ import annotations`
    # so that forward-ref strings like "list[MessageBlock]" resolve correctly
    # even when the module was loaded under the alias "api._legacy_schemas".
    _MessageBlock = _legacy_exports.get("MessageBlock")
    if _MessageBlock is not None:
        try:
            from pydantic import BaseModel as _BaseModel
            _types_ns: dict[str, Any] = {"MessageBlock": _MessageBlock}
            for _obj in _legacy_exports.values():
                if isinstance(_obj, type) and issubclass(_obj, _BaseModel):
                    try:
                        _obj.model_rebuild(_types_namespace=_types_ns)
                    except Exception:
                        pass
        except Exception:
            pass


__all__ = sorted(
    set(
        list(_legacy_exports.keys())
        + ["WorkflowDefinitionSchema", "WorkflowEdge", "WorkflowStep"]
    )
)
