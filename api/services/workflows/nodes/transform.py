"""Transform node — reshapes data using a jq-like field mapping.

step_config:
    mapping: dict[str, str] — output_field → input expression
        Expressions:
          - "input.key"         → read from step inputs
          - "literal:value"     → literal string
          - "input.key | upper" → basic pipe transforms (upper, lower, strip, int, float)
    template: str           — optional Jinja2-style template (fallback if no mapping)

Returns a dict with the mapped fields.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowStep
from api.services.workflows.nodes import register

logger = logging.getLogger(__name__)


@register("transform")
def handle_transform(
    step: WorkflowStep,
    inputs: dict[str, Any],
    on_event: Optional[Callable] = None,
) -> dict[str, Any]:
    cfg = step.step_config
    mapping = cfg.get("mapping", {})

    if not mapping:
        # Passthrough mode — return inputs as-is
        return dict(inputs)

    result: dict[str, Any] = {}
    for out_key, expr in mapping.items():
        result[out_key] = _evaluate_expr(expr, inputs)
    return result


def _evaluate_expr(expr: str, inputs: dict[str, Any]) -> Any:
    """Evaluate a simple transform expression."""
    if expr.startswith("literal:"):
        return expr[len("literal:"):]

    # Handle pipe transforms: "input.key | upper"
    parts = [p.strip() for p in expr.split("|")]
    base_expr = parts[0]
    transforms = parts[1:]

    # Resolve base value
    if base_expr.startswith("input."):
        key = base_expr[len("input."):]
        value = inputs.get(key, "")
    else:
        value = inputs.get(base_expr, base_expr)

    # Apply transforms
    for t in transforms:
        value = _apply_transform(t, value)
    return value


def _to_json(v: Any) -> str:
    import json as _json
    return _json.dumps(v, default=str)

def _from_json(v: Any) -> Any:
    import json as _json
    return _json.loads(str(v))

def _to_base64(v: Any) -> str:
    import base64 as _b64
    return _b64.b64encode(str(v).encode()).decode()

def _from_base64(v: Any) -> str:
    import base64 as _b64
    return _b64.b64decode(str(v).encode()).decode()


_TRANSFORMS = {
    "upper": lambda v: str(v).upper(),
    "lower": lambda v: str(v).lower(),
    "strip": lambda v: str(v).strip(),
    "int": lambda v: int(v),
    "float": lambda v: float(v),
    "str": lambda v: str(v),
    "len": lambda v: len(v) if hasattr(v, "__len__") else 0,
    "keys": lambda v: list(v.keys()) if isinstance(v, dict) else [],
    "values": lambda v: list(v.values()) if isinstance(v, dict) else [],
    "json": _to_json,
    "from_json": _from_json,
    "base64": _to_base64,
    "from_base64": _from_base64,
    "first": lambda v: v[0] if isinstance(v, (list, tuple)) and v else v,
    "last": lambda v: v[-1] if isinstance(v, (list, tuple)) and v else v,
    "unique": lambda v: list(set(v)) if isinstance(v, list) else v,
    "flatten": lambda v: [item for sub in v for item in (sub if isinstance(sub, list) else [sub])] if isinstance(v, list) else v,
}


def _apply_transform(name: str, value: Any) -> Any:
    fn = _TRANSFORMS.get(name.lower())
    if fn is None:
        logger.warning("Unknown transform '%s' — skipping", name)
        return value
    try:
        return fn(value)
    except (ValueError, TypeError) as exc:
        logger.warning("Transform '%s' failed on %r: %s", name, value, exc)
        return value
