"""Math calculation tool — allows agents to compute expressions precisely.

When the LLM encounters a formula from a PDF and needs to calculate the result,
it calls this tool instead of doing mental math. Ensures exact arithmetic.
"""

from __future__ import annotations

import re
from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.math_eval import safe_math_eval


class MathCalculationTool(AgentTool):
    """Execute mathematical expressions safely and return precise results.

    The agent provides:
    - expression: the math expression to evaluate (e.g., "(100 / 1.08) + (200 / 1.08**2)")
    - formula_source: where the formula came from (citation ref)
    - variables: dict of variable names → values for display
    """

    metadata = ToolMetadata(
        tool_id="math.calculate",
        action_class="read",
        risk_level="low",
        required_permissions=[],
        execution_policy="auto_execute",
        description="Evaluate a mathematical expression precisely. Use for any calculation from PDF formulas.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        events: list[ToolTraceEvent] = []

        expression = str(params.get("expression") or "").strip()
        formula_source = str(params.get("formula_source") or "").strip()
        variables = params.get("variables") or {}

        if not expression:
            return ToolExecutionResult(
                output="No expression provided. Pass an expression like '(100 / 1.08) + (200 / 1.08**2)'",
                events=events,
                success=False,
            )

        # Log the computation
        events.append(ToolTraceEvent(
            tool_id=self.metadata.tool_id,
            action="compute",
            detail=f"Evaluating: {expression[:200]}",
        ))

        result = safe_math_eval(expression)

        if isinstance(result, str) and ("error" in result.lower() or "blocked" in result.lower()):
            return ToolExecutionResult(
                output=f"Calculation failed: {result}",
                events=events,
                success=False,
            )

        # Format the output with the computation details
        lines = []
        if formula_source:
            lines.append(f"Formula source: {formula_source}")
        if variables:
            lines.append("Variables:")
            for var_name, var_value in variables.items():
                lines.append(f"  {var_name} = {var_value}")
        lines.append(f"Expression: {expression}")
        lines.append(f"Result: {result}")

        # If it's a float, show a reasonable precision
        if isinstance(result, float):
            if abs(result) > 1000:
                lines.append(f"Formatted: {result:,.2f}")
            elif abs(result) < 0.01:
                lines.append(f"Formatted: {result:.6f}")
            else:
                lines.append(f"Formatted: {result:.4f}")

        return ToolExecutionResult(
            output="\n".join(lines),
            events=events,
            success=True,
        )


class MathVerifyTool(AgentTool):
    """Verify a calculation by computing it two different ways.

    Used for self-verification of multi-step derivations.
    The agent provides two expressions that should produce the same result.
    """

    metadata = ToolMetadata(
        tool_id="math.verify",
        action_class="read",
        risk_level="low",
        required_permissions=[],
        execution_policy="auto_execute",
        description="Verify a calculation by computing two equivalent expressions. Flags disagreements.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        events: list[ToolTraceEvent] = []

        expr_a = str(params.get("expression_a") or params.get("expression") or "").strip()
        expr_b = str(params.get("expression_b") or params.get("verification") or "").strip()
        tolerance = float(params.get("tolerance") or 0.01)

        if not expr_a:
            return ToolExecutionResult(
                output="No expression provided.",
                events=events,
                success=False,
            )

        result_a = safe_math_eval(expr_a)

        if not expr_b:
            # Single expression — just compute
            return ToolExecutionResult(
                output=f"Expression: {expr_a}\nResult: {result_a}",
                events=events,
                success=isinstance(result_a, (int, float)),
            )

        result_b = safe_math_eval(expr_b)

        events.append(ToolTraceEvent(
            tool_id=self.metadata.tool_id,
            action="verify",
            detail=f"Comparing: {expr_a[:80]} vs {expr_b[:80]}",
        ))

        # Compare results
        if isinstance(result_a, (int, float)) and isinstance(result_b, (int, float)):
            diff = abs(result_a - result_b)
            matches = diff <= tolerance * max(1, abs(result_a), abs(result_b))

            lines = [
                f"Method A: {expr_a}",
                f"Result A: {result_a}",
                f"Method B: {expr_b}",
                f"Result B: {result_b}",
                f"Difference: {diff:.6f}",
                f"Verification: {'PASS — results agree' if matches else 'FAIL — results disagree!'}",
            ]

            if not matches:
                lines.append(f"WARNING: The two methods disagree by {diff:.4f}. Check intermediate steps.")

            return ToolExecutionResult(
                output="\n".join(lines),
                events=events,
                success=matches,
            )

        return ToolExecutionResult(
            output=f"Method A result: {result_a}\nMethod B result: {result_b}\nCannot compare non-numeric results.",
            events=events,
            success=False,
        )
