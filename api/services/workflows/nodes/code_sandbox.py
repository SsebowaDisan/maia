"""Code sandbox node — executes a user-defined Python expression safely.

step_config:
    code: str — Python expression to evaluate (statements NOT allowed)
    allowed_builtins: list[str] — whitelist of builtins (default: safe subset)

All step inputs are available as local variables.
Returns {"result": <expression_result>}.

Security:
  - Only eval() is allowed (no exec/statements)
  - Restricted builtins — no __import__, getattr, setattr, delattr, eval, exec, compile
  - Blocked dunder attribute access in code string
  - Code length capped at 2000 chars
  - Timeout enforced by parent executor
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowStep
from api.services.workflows.nodes import register

logger = logging.getLogger(__name__)

_SAFE_BUILTINS = {
    "abs", "all", "any", "bool", "dict", "enumerate", "filter",
    "float", "frozenset", "int", "isinstance", "len", "list",
    "map", "max", "min", "range", "reversed", "round", "set",
    "sorted", "str", "sum", "tuple", "zip",
}

# Patterns that indicate sandbox escape attempts
_BLOCKED_PATTERNS = re.compile(
    r"__\w+__|"           # dunder attributes (__class__, __mro__, __import__, etc.)
    r"\bimport\b|"        # import keyword
    r"\bexec\s*\(|"       # exec() call
    r"\beval\s*\(|"       # nested eval() call
    r"\bcompile\s*\(|"    # compile() call
    r"\bgetattr\s*\(|"    # getattr() call
    r"\bsetattr\s*\(|"    # setattr() call
    r"\bdelattr\s*\(|"    # delattr() call
    r"\bglobals\s*\(|"    # globals() call
    r"\blocals\s*\(|"     # locals() call
    r"\bvars\s*\(|"       # vars() call
    r"\bopen\s*\(|"       # open() call
    r"\bbreakpoint\s*\(|" # breakpoint() call
    r"\bdir\s*\(",        # dir() call
    re.IGNORECASE,
)

_MAX_CODE_LENGTH = 2000


@register("code")
def handle_code(
    step: WorkflowStep,
    inputs: dict[str, Any],
    on_event: Optional[Callable] = None,
) -> dict[str, Any]:
    code = step.step_config.get("code", "")
    if not code:
        raise ValueError(f"Step {step.step_id}: code node requires 'code' in step_config")

    if len(code) > _MAX_CODE_LENGTH:
        raise ValueError(f"Step {step.step_id}: code exceeds {_MAX_CODE_LENGTH} char limit")

    # Block dangerous patterns before any evaluation
    if _BLOCKED_PATTERNS.search(code):
        raise ValueError(
            f"Step {step.step_id}: code contains blocked pattern "
            f"(dunder access, import, exec, eval, getattr, open, etc.)"
        )

    # Build a restricted builtins dict — only safe pure functions
    import builtins as _builtins_mod
    allowed_names = step.step_config.get("allowed_builtins", list(_SAFE_BUILTINS))
    # Intersect with our safe set — user cannot add unsafe builtins
    effective_names = set(allowed_names) & _SAFE_BUILTINS
    safe_builtins = {k: getattr(_builtins_mod, k) for k in effective_names if hasattr(_builtins_mod, k)}
    # Explicitly add constants
    safe_builtins["True"] = True
    safe_builtins["False"] = False
    safe_builtins["None"] = None

    namespace: dict[str, Any] = {"__builtins__": safe_builtins, **inputs}

    try:
        result = eval(compile(code, "<sandbox>", "eval"), namespace)  # noqa: S307
    except SyntaxError as exc:
        raise ValueError(
            f"Step {step.step_id}: code must be a single expression, not statements. "
            f"Error: {exc}"
        ) from exc

    return {"result": result}
