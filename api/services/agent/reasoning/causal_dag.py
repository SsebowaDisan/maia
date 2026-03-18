"""Causal Reasoning DAG (Innovation #4).

Builds a dependency graph from planned steps, detects conflicts,
computes optimal execution order, and provides impact analysis when
steps fail.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from api.services.agent.llm_runtime import call_json_response, has_openai_credentials

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CausalNode:
    """A single step in the causal graph."""

    step_id: str
    tool_id: str
    expected_output_type: str = ""
    side_effects: list[str] = field(default_factory=list)


@dataclass
class CausalEdge:
    """A directed dependency between two steps."""

    from_id: str
    to_id: str
    dependency_type: str  # data_flow | precondition | enables | conflicts
    param_mapping: dict[str, str] = field(default_factory=dict)


@dataclass
class CausalGraph:
    """The full dependency DAG for a plan."""

    nodes: list[CausalNode] = field(default_factory=list)
    edges: list[CausalEdge] = field(default_factory=list)

    def _adjacency(self) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            if edge.dependency_type != "conflicts":
                adj[edge.from_id].append(edge.to_id)
        return adj

    def _reverse_adjacency(self) -> dict[str, list[str]]:
        rev: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            if edge.dependency_type != "conflicts":
                rev[edge.to_id].append(edge.from_id)
        return rev


# ---------------------------------------------------------------------------
# CausalDAG
# ---------------------------------------------------------------------------

class CausalDAG:
    """Build and query causal dependency graphs from planned steps."""

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build_from_steps(self, steps: list[dict[str, Any]]) -> CausalGraph:
        """Construct a CausalGraph from a list of step dicts.

        Uses LLM to infer dependencies when credentials are available;
        otherwise falls back to sequential ordering.
        """
        nodes: list[CausalNode] = []
        for idx, step in enumerate(steps):
            step_id = str(step.get("step_id") or f"step_{idx + 1}")
            tool_id = str(step.get("tool_id") or "")
            nodes.append(
                CausalNode(
                    step_id=step_id,
                    tool_id=tool_id,
                    expected_output_type=str(step.get("expected_output_type") or ""),
                    side_effects=list(step.get("side_effects") or []),
                )
            )

        edges = self._infer_edges(steps, nodes)
        return CausalGraph(nodes=nodes, edges=edges)

    def _infer_edges(
        self,
        steps: list[dict[str, Any]],
        nodes: list[CausalNode],
    ) -> list[CausalEdge]:
        """Infer edges via LLM or fall back to sequential chain."""
        if not has_openai_credentials() or len(nodes) < 2:
            return self._sequential_edges(nodes)

        step_summaries = [
            {
                "step_id": n.step_id,
                "tool_id": n.tool_id,
                "title": str(steps[i].get("title") or "")[:80] if i < len(steps) else "",
            }
            for i, n in enumerate(nodes)
        ]

        prompt = (
            "Analyze dependencies between these execution steps.\n\n"
            f"Steps: {json.dumps(step_summaries)}\n\n"
            "For each dependency, identify:\n"
            '- dependency_type: one of "data_flow", "precondition", "enables", "conflicts"\n'
            "- param_mapping: which output feeds which input (if data_flow)\n\n"
            "Return JSON:\n"
            '{"edges": [{"from_id": "step_1", "to_id": "step_2", '
            '"dependency_type": "data_flow", "param_mapping": {}}]}'
        )

        try:
            payload = call_json_response(
                system_prompt="You are a dependency analysis engine. Output strict JSON only.",
                user_prompt=prompt,
                temperature=0.0,
                timeout_seconds=12,
                max_tokens=800,
            )
        except Exception:
            logger.exception("CausalDAG: LLM edge inference failed — using sequential fallback")
            return self._sequential_edges(nodes)

        if not isinstance(payload, dict):
            return self._sequential_edges(nodes)

        raw_edges = payload.get("edges")
        if not isinstance(raw_edges, list):
            return self._sequential_edges(nodes)

        valid_ids = {n.step_id for n in nodes}
        edges: list[CausalEdge] = []
        for item in raw_edges:
            if not isinstance(item, dict):
                continue
            from_id = str(item.get("from_id") or "")
            to_id = str(item.get("to_id") or "")
            dep_type = str(item.get("dependency_type") or "precondition")
            if from_id not in valid_ids or to_id not in valid_ids:
                continue
            if from_id == to_id:
                continue
            if dep_type not in ("data_flow", "precondition", "enables", "conflicts"):
                dep_type = "precondition"
            edges.append(
                CausalEdge(
                    from_id=from_id,
                    to_id=to_id,
                    dependency_type=dep_type,
                    param_mapping=dict(item.get("param_mapping") or {}),
                )
            )

        return edges if edges else self._sequential_edges(nodes)

    @staticmethod
    def _sequential_edges(nodes: list[CausalNode]) -> list[CausalEdge]:
        """Fallback: chain steps in sequential order."""
        edges: list[CausalEdge] = []
        for i in range(len(nodes) - 1):
            edges.append(
                CausalEdge(
                    from_id=nodes[i].step_id,
                    to_id=nodes[i + 1].step_id,
                    dependency_type="precondition",
                )
            )
        return edges

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def detect_conflicts(self, graph: CausalGraph) -> list[tuple[str, str]]:
        """Return pairs of step_ids that have a 'conflicts' edge."""
        return [
            (edge.from_id, edge.to_id)
            for edge in graph.edges
            if edge.dependency_type == "conflicts"
        ]

    # ------------------------------------------------------------------
    # Optimal execution order
    # ------------------------------------------------------------------

    def optimal_execution_order(self, graph: CausalGraph) -> list[str]:
        """Topological sort respecting dependencies (Kahn's algorithm)."""
        adj = graph._adjacency()
        in_degree: dict[str, int] = {n.step_id: 0 for n in graph.nodes}
        for edge in graph.edges:
            if edge.dependency_type != "conflicts":
                in_degree.setdefault(edge.to_id, 0)
                in_degree[edge.to_id] += 1

        queue: deque[str] = deque(
            nid for nid, deg in in_degree.items() if deg == 0
        )
        order: list[str] = []
        while queue:
            current = queue.popleft()
            order.append(current)
            for neighbour in adj.get(current, []):
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        # If cycle detected, append remaining nodes at end.
        remaining = [n.step_id for n in graph.nodes if n.step_id not in set(order)]
        order.extend(remaining)
        return order

    # ------------------------------------------------------------------
    # Impact analysis
    # ------------------------------------------------------------------

    def predict_impact(
        self,
        graph: CausalGraph,
        failed_step_id: str,
    ) -> list[str]:
        """Return all downstream step_ids affected by a failure."""
        adj = graph._adjacency()
        affected: list[str] = []
        visited: set[str] = set()
        queue: deque[str] = deque()
        for neighbour in adj.get(failed_step_id, []):
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append(neighbour)

        while queue:
            current = queue.popleft()
            affected.append(current)
            for neighbour in adj.get(current, []):
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)

        return affected

    # ------------------------------------------------------------------
    # Bypass suggestion
    # ------------------------------------------------------------------

    def suggest_bypass(
        self,
        graph: CausalGraph,
        failed_step_id: str,
        available_tools: list[str],
    ) -> list[dict[str, Any]]:
        """Suggest alternative paths when a step fails."""
        if not has_openai_credentials():
            return []

        failed_node = None
        for n in graph.nodes:
            if n.step_id == failed_step_id:
                failed_node = n
                break
        if failed_node is None:
            return []

        affected = self.predict_impact(graph, failed_step_id)

        prompt = (
            "A step failed in an execution plan. Suggest alternative tool sequences "
            "to bypass the failure and still reach the downstream goals.\n\n"
            f"Failed step: tool_id={failed_node.tool_id}, step_id={failed_step_id}\n"
            f"Downstream affected steps: {affected}\n"
            f"Available tools: {json.dumps(available_tools[:40])}\n\n"
            "Return JSON:\n"
            '{"alternatives": [{"tool_id": "...", "title": "...", "params": {}, '
            '"rationale": "..."}]}'
        )

        try:
            payload = call_json_response(
                system_prompt="You are a plan recovery engine. Output strict JSON only.",
                user_prompt=prompt,
                temperature=0.3,
                timeout_seconds=12,
                max_tokens=600,
            )
        except Exception:
            logger.exception("CausalDAG: bypass suggestion LLM call failed")
            return []

        if not isinstance(payload, dict):
            return []
        alternatives = payload.get("alternatives")
        return alternatives if isinstance(alternatives, list) else []
