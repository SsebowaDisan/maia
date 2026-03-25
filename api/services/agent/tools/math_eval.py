"""Safe math evaluator — executes mathematical expressions from PDF formulas.

Used when the LLM needs to compute results from extracted formulas.
Only allows safe math operations — no imports, no file access, no exec.

Usage:
    result = safe_math_eval("(100 / (1 + 0.08)**1) + (200 / (1 + 0.08)**2)")
    # → 259.3...
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

# Allowed operators
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Allowed math functions (safe subset)
_SAFE_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "int": int,
    "float": float,
    # Math module functions
    "sqrt": math.sqrt,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "ceil": math.ceil,
    "floor": math.floor,
    "factorial": math.factorial,
    "pow": math.pow,
    "pi": math.pi,
    "e": math.e,
}


def safe_math_eval(expression: str) -> float | int | str:
    """Evaluate a mathematical expression safely.

    Supports: arithmetic, exponents, parentheses, math functions.
    Blocks: imports, attribute access, function definitions, file I/O.

    Returns the numeric result or an error string.
    """
    expr = str(expression or "").strip()
    if not expr:
        return "Empty expression"
    if len(expr) > 1000:
        return "Expression too long (max 1000 chars)"

    # Block dangerous patterns
    for blocked in ("import", "__", "exec", "eval", "open", "os.", "sys.", "subprocess"):
        if blocked in expr.lower():
            return f"Blocked: contains '{blocked}'"

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return f"Syntax error: {e.msg}"

    try:
        result = _eval_node(tree.body)
        if isinstance(result, (int, float)):
            return result
        return str(result)
    except Exception as e:
        return f"Evaluation error: {e}"


def _eval_node(node: ast.AST) -> Any:
    """Recursively evaluate AST nodes — only allows safe operations."""

    # Numbers
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    # Unary operators (-x, +x)
    if isinstance(node, ast.UnaryOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand))

    # Binary operators (x + y, x ** y, etc.)
    if isinstance(node, ast.BinOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        # Safety: prevent absurdly large exponents
        if isinstance(node.op, ast.Pow) and isinstance(right, (int, float)) and abs(right) > 1000:
            raise ValueError("Exponent too large (max 1000)")
        return op(left, right)

    # Comparison operators (for conditional-like expressions)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator)
            if isinstance(op, ast.Lt):
                if not (left < right): return False
            elif isinstance(op, ast.LtE):
                if not (left <= right): return False
            elif isinstance(op, ast.Gt):
                if not (left > right): return False
            elif isinstance(op, ast.GtE):
                if not (left >= right): return False
            elif isinstance(op, ast.Eq):
                if not (left == right): return False
            else:
                raise ValueError(f"Unsupported comparison: {type(op).__name__}")
            left = right
        return True

    # Function calls (only safe functions)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            fn = _SAFE_FUNCTIONS.get(node.func.id)
            if fn is None:
                raise ValueError(f"Unknown function: {node.func.id}")
            args = [_eval_node(arg) for arg in node.args]
            return fn(*args)
        raise ValueError("Only simple function calls allowed")

    # Variable names (only safe constants)
    if isinstance(node, ast.Name):
        val = _SAFE_FUNCTIONS.get(node.id)
        if val is not None and isinstance(val, (int, float)):
            return val
        raise ValueError(f"Unknown variable: {node.id}")

    # List/tuple for multi-arg functions like sum([1,2,3])
    if isinstance(node, ast.List):
        return [_eval_node(elt) for elt in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt) for elt in node.elts)

    raise ValueError(f"Unsupported expression type: {type(node).__name__}")
