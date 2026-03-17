"""B6-01 — Workflow definition schema.

Responsibility: Pydantic schema for multi-agent workflow definitions.
A workflow is a DAG of agent steps with conditional edges.
"""
from __future__ import annotations

from typing import Any, Literal, Optional  # noqa: F401 — Literal used in WorkflowStep

from pydantic import BaseModel, Field, field_validator


StepType = Literal[
    "agent", "http_request", "condition", "code", "transform",
    "delay", "foreach", "merge", "switch",
]


class WorkflowStep(BaseModel):
    """One step within the workflow — agent or deterministic node."""

    step_id: str
    agent_id: str = ""
    """Required when step_type is 'agent'. Ignored for deterministic nodes."""
    step_type: StepType = "agent"
    """Node type. 'agent' runs an LLM agent; others are deterministic."""
    step_config: dict[str, Any] = {}
    """Type-specific configuration (e.g. url/method for http_request)."""
    input_mapping: dict[str, str] = {}
    """Maps input keys to prior step output keys or literal values.
    e.g. {"query": "step1.result", "context": "literal:Company=Acme"}
    """
    output_key: str = Field(pattern=r"^[a-zA-Z_]\w{0,63}$")
    """Key under which this step's result is stored for downstream steps."""
    description: str = ""
    timeout_s: int = Field(default=300, ge=1, le=3600)
    """Per-step timeout in seconds. Overrides the global default."""
    max_retries: int = Field(default=0, ge=0, le=10)
    """Number of retry attempts on failure (exponential backoff)."""

    @field_validator("step_config")
    @classmethod
    def validate_step_config(cls, config: dict, info: Any) -> dict:
        """Validate that step_config contains required fields for each step_type."""
        step_type = info.data.get("step_type", "agent")
        required: dict[str, list[str]] = {
            "http_request": ["url"],
            "condition": ["expression"],
            "code": ["code"],
            "switch": ["value_key"],
        }
        missing = [f for f in required.get(step_type, []) if f not in config]
        if missing:
            raise ValueError(
                f"step_type '{step_type}' requires these fields in step_config: {missing}"
            )
        return config

    # ── B6: Typed data contracts ──────────────────────────────────────────────
    output_schema: Optional[dict[str, Any]] = None
    """JSON Schema object that the step output must conform to."""
    format_hint: Optional[Literal["json", "markdown", "plaintext"]] = None
    """Hint to downstream steps about how to parse this step's output."""


class WorkflowEdge(BaseModel):
    """Directed edge between two workflow steps with an optional condition."""

    from_step: str
    to_step: str
    condition: Optional[str] = None
    """Optional Python-expression condition string evaluated against prior outputs.
    Examples:
      - "output.status == 'success'"
      - "output.confidence > 0.8"
      - None → always execute
    """


class WorkflowDefinitionSchema(BaseModel):
    """Top-level workflow definition."""

    workflow_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str
    description: str = ""
    steps: list[WorkflowStep]
    edges: list[WorkflowEdge]
    version: str = "1.0.0"
    max_computer_use_sessions: int = Field(default=3, ge=0, le=10)
    """Maximum number of concurrent Computer Use sessions in this workflow."""

    @field_validator("steps")
    @classmethod
    def steps_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("A workflow must have at least one step.")
        return v

    @field_validator("edges")
    @classmethod
    def edges_reference_valid_steps(cls, edges: list, info: Any) -> list:
        steps_data = info.data.get("steps") or []
        step_ids = {s.step_id for s in steps_data}
        for edge in edges:
            if edge.from_step not in step_ids:
                raise ValueError(f"Edge from_step '{edge.from_step}' not found in steps.")
            if edge.to_step not in step_ids:
                raise ValueError(f"Edge to_step '{edge.to_step}' not found in steps.")
        return edges

    def topological_order(self) -> list[str]:
        """Return step_ids in topological (dependency) order via Kahn's algorithm."""
        from collections import defaultdict, deque

        in_degree: dict[str, int] = {s.step_id: 0 for s in self.steps}
        adj: dict[str, list[str]] = defaultdict(list)

        for edge in self.edges:
            adj[edge.from_step].append(edge.to_step)
            in_degree[edge.to_step] += 1

        queue: deque[str] = deque(sid for sid, deg in in_degree.items() if deg == 0)
        order: list[str] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.steps):
            raise ValueError("Workflow contains a cycle — DAG required.")

        return order

    def get_step(self, step_id: str) -> Optional[WorkflowStep]:
        return next((s for s in self.steps if s.step_id == step_id), None)

    def outgoing_edges(self, step_id: str) -> list[WorkflowEdge]:
        return [e for e in self.edges if e.from_step == step_id]
