"""Stage Contracts — typed I/O contracts for workflow steps.

Inspired by AutoResearchClaw's pipeline contracts pattern.
Each step can declare what inputs it requires, what outputs it produces,
a Definition of Done predicate, and retry limits. The workflow executor
validates these at step boundaries.

Usage:
    contract = StageContract(
        required_inputs=["query"],
        expected_outputs=["results", "count"],
        definition_of_done="count > 0",
        max_retries=2,
    )
    contract.validate_inputs({"query": "revenue trends"})  # passes
    contract.validate_outputs({"results": [...], "count": 5})  # passes
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class StageContract:
    """Declares the I/O contract for a workflow step."""

    def __init__(
        self,
        *,
        required_inputs: list[str] | None = None,
        optional_inputs: list[str] | None = None,
        expected_outputs: list[str] | None = None,
        definition_of_done: str = "",
        max_retries: int = 0,
        timeout_s: int = 300,
    ):
        self.required_inputs = list(required_inputs or [])
        self.optional_inputs = list(optional_inputs or [])
        self.expected_outputs = list(expected_outputs or [])
        self.definition_of_done = definition_of_done.strip()
        self.max_retries = max(0, min(max_retries, 10))
        self.timeout_s = max(1, min(timeout_s, 3600))

    def validate_inputs(self, inputs: dict[str, Any]) -> list[str]:
        """Check that all required inputs are present and non-empty.

        Returns list of error messages (empty = valid).
        """
        errors: list[str] = []
        for key in self.required_inputs:
            if key not in inputs:
                errors.append(f"Missing required input: '{key}'")
            elif _is_empty(inputs[key]):
                errors.append(f"Required input '{key}' is empty")
        return errors

    def validate_outputs(self, outputs: dict[str, Any]) -> list[str]:
        """Check that all expected outputs are present.

        Returns list of error messages (empty = valid).
        """
        if not self.expected_outputs:
            return []
        errors: list[str] = []
        if not isinstance(outputs, dict):
            return [f"Expected dict output, got {type(outputs).__name__}"]
        for key in self.expected_outputs:
            if key not in outputs:
                errors.append(f"Missing expected output: '{key}'")
        return errors

    def check_definition_of_done(self, outputs: dict[str, Any]) -> bool:
        """Evaluate the DoD predicate against outputs.

        Returns True if no DoD is defined or if the predicate passes.
        """
        if not self.definition_of_done:
            return True
        return _evaluate_dod(self.definition_of_done, outputs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_inputs": self.required_inputs,
            "optional_inputs": self.optional_inputs,
            "expected_outputs": self.expected_outputs,
            "definition_of_done": self.definition_of_done,
            "max_retries": self.max_retries,
            "timeout_s": self.timeout_s,
        }


# ── Built-in contracts for known step types ───────────────────────────────────

STEP_TYPE_CONTRACTS: dict[str, StageContract] = {
    "knowledge_search": StageContract(
        required_inputs=["query"],
        expected_outputs=["results", "count", "query"],
        definition_of_done="count > 0",
        max_retries=1,
    ),
    "http_request": StageContract(
        required_inputs=[],
        expected_outputs=[],
        definition_of_done="",
        max_retries=2,
        timeout_s=30,
    ),
    "condition": StageContract(
        required_inputs=[],
        expected_outputs=["result"],
        definition_of_done="",
    ),
    "transform": StageContract(
        required_inputs=[],
        expected_outputs=[],
    ),
    "code": StageContract(
        required_inputs=[],
        expected_outputs=["result"],
    ),
}


def get_contract(step_type: str) -> StageContract | None:
    """Return the built-in contract for a step type, or None."""
    return STEP_TYPE_CONTRACTS.get(step_type)


def validate_step_boundary(
    *,
    step_type: str,
    phase: str,
    data: dict[str, Any],
) -> list[str]:
    """Validate inputs or outputs against the step type's contract.

    Args:
        step_type: The workflow step type.
        phase: "input" or "output".
        data: The inputs or outputs dict to validate.

    Returns:
        List of validation errors (empty = valid).
    """
    contract = get_contract(step_type)
    if not contract:
        return []
    if phase == "input":
        return contract.validate_inputs(data)
    if phase == "output":
        errors = contract.validate_outputs(data)
        if not errors and not contract.check_definition_of_done(data):
            errors.append(f"Definition of Done not met: {contract.definition_of_done}")
        return errors
    return []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


_SAFE_DOD_PATTERN = re.compile(r"^[a-zA-Z_]\w*\s*(>|<|>=|<=|==|!=)\s*\d+$")


def _evaluate_dod(expression: str, outputs: dict[str, Any]) -> bool:
    """Safely evaluate a simple DoD expression like 'count > 0'."""
    expr = expression.strip()
    if not _SAFE_DOD_PATTERN.match(expr):
        logger.debug("DoD expression too complex, skipping: %s", expr)
        return True
    try:
        result = eval(expr, {"__builtins__": {}}, outputs)  # noqa: S307
        return bool(result)
    except Exception:
        return True
