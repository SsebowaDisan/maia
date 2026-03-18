"""Hierarchical goal decomposition for multi-agent tasks.

Decomposes a high-level goal into a tree of sub-goals, assigns each to the
most capable agent, and merges the results back into a coherent answer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class GoalNode:
    """A single node in the goal decomposition tree."""
    goal_text: str
    assigned_agent_id: str | None = None
    sub_goals: list[GoalNode] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    priority: int = 0  # lower = higher priority

    def leaf_nodes(self) -> list[GoalNode]:
        """Return all leaf nodes (actionable sub-goals) in DFS order."""
        if not self.sub_goals:
            return [self]
        leaves: list[GoalNode] = []
        for child in self.sub_goals:
            leaves.extend(child.leaf_nodes())
        return leaves


@dataclass
class GoalTree:
    """Root container for a hierarchical goal decomposition."""
    root: GoalNode

    def all_leaves(self) -> list[GoalNode]:
        return self.root.leaf_nodes()

    def assigned_agents(self) -> set[str]:
        """Return set of all agent IDs referenced in the tree."""
        ids: set[str] = set()
        self._collect_agents(self.root, ids)
        return ids

    def _collect_agents(self, node: GoalNode, ids: set[str]) -> None:
        if node.assigned_agent_id:
            ids.add(node.assigned_agent_id)
        for child in node.sub_goals:
            self._collect_agents(child, ids)


# ── Decomposer ────────────────────────────────────────────────────────────────

class GoalDecomposer:
    """Decomposes a parent goal into sub-goals and assigns agents."""

    def decompose_goal(
        self,
        parent_goal: str,
        available_agents: list[dict[str, Any]],
    ) -> GoalTree:
        """Use LLM to decompose a goal into a tree of sub-goals.

        Args:
            parent_goal: High-level natural-language goal.
            available_agents: List of dicts with at least ``id`` and ``description``.

        Returns:
            A GoalTree with sub-goals assigned to agents.
        """
        from api.services.agents.llm_utils import call_llm_json

        agent_descriptions = "\n".join(
            f"- id={a.get('id', 'unknown')}  capabilities={a.get('description', 'general')}"
            for a in available_agents
        )

        prompt = (
            "You are a task decomposition engine. Break the following goal into "
            "concrete sub-goals and assign each to the most capable agent.\n\n"
            f"GOAL: {parent_goal}\n\n"
            f"AVAILABLE AGENTS:\n{agent_descriptions}\n\n"
            "Reply with JSON:\n"
            "{\n"
            '  "sub_goals": [\n'
            "    {\n"
            '      "goal_text": "<specific sub-task>",\n'
            '      "assigned_agent_id": "<agent id>",\n'
            '      "dependencies": ["<goal_text of a prerequisite, if any>"],\n'
            '      "priority": <int, 0=highest>\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Each sub-goal should be independently actionable\n"
            "- Assign to the agent whose capabilities best match\n"
            "- Use dependencies only when one sub-goal truly requires another's output\n"
            "- Keep sub-goals to 2-6 items (don't over-decompose)"
        )

        try:
            result = call_llm_json(prompt, max_tokens=800)
            raw_goals = result.get("sub_goals", [])
        except Exception as exc:
            logger.warning("Goal decomposition LLM call failed: %s", exc)
            # Fallback: single goal assigned to first available agent
            fallback_agent = available_agents[0].get("id", "unknown") if available_agents else None
            return GoalTree(
                root=GoalNode(
                    goal_text=parent_goal,
                    assigned_agent_id=fallback_agent,
                )
            )

        # Build tree
        children: list[GoalNode] = []
        for item in raw_goals:
            children.append(GoalNode(
                goal_text=str(item.get("goal_text", "")),
                assigned_agent_id=str(item.get("assigned_agent_id", "")) or None,
                dependencies=[str(d) for d in item.get("dependencies", [])],
                priority=int(item.get("priority", 0)),
            ))

        # Sort by priority
        children.sort(key=lambda n: n.priority)

        root = GoalNode(
            goal_text=parent_goal,
            sub_goals=children,
        )

        return GoalTree(root=root)

    def merge_results(
        self,
        goal_tree: GoalTree,
        agent_results: dict[str, Any],
    ) -> str:
        """Combine sub-goal results into a coherent parent-goal answer.

        Args:
            goal_tree: The decomposed goal tree.
            agent_results: Mapping of goal_text -> agent output string.

        Returns:
            A synthesized answer combining all sub-goal results.
        """
        leaves = goal_tree.all_leaves()
        parts: list[str] = []
        missing: list[str] = []

        for node in leaves:
            result = agent_results.get(node.goal_text)
            if result:
                parts.append(
                    f"## {node.goal_text}\n"
                    f"(Agent: {node.assigned_agent_id})\n\n"
                    f"{result}"
                )
            else:
                missing.append(node.goal_text)

        if not parts:
            return "(No sub-goal results were produced.)"

        # Use LLM to synthesize if we have multiple parts
        if len(parts) > 1:
            return self._llm_merge(goal_tree.root.goal_text, parts, missing)

        merged = "\n\n---\n\n".join(parts)
        if missing:
            merged += "\n\n**Incomplete sub-goals:**\n" + "\n".join(f"- {m}" for m in missing)
        return merged

    def validate_completeness(
        self,
        goal_tree: GoalTree,
        agent_results: dict[str, Any],
    ) -> list[str]:
        """Return a list of sub-goals that have no result (unmet goals).

        Args:
            goal_tree: The decomposed goal tree.
            agent_results: Mapping of goal_text -> agent output.

        Returns:
            List of goal_text strings that are missing results.
        """
        unmet: list[str] = []
        for node in goal_tree.all_leaves():
            if not agent_results.get(node.goal_text):
                unmet.append(node.goal_text)
        return unmet

    # ── Private helpers ───────────────────────────────────────────────────

    def _llm_merge(
        self,
        parent_goal: str,
        result_parts: list[str],
        missing: list[str],
    ) -> str:
        """Use LLM to create a coherent synthesis of sub-goal results."""
        try:
            from api.services.agents.llm_utils import call_llm_json

            combined_input = "\n\n---\n\n".join(result_parts)
            missing_note = ""
            if missing:
                missing_note = (
                    "\n\nNOTE: These sub-goals could not be completed:\n"
                    + "\n".join(f"- {m}" for m in missing)
                )

            prompt = (
                "You are synthesizing results from multiple agents into one coherent answer.\n\n"
                f"ORIGINAL GOAL: {parent_goal}\n\n"
                f"SUB-GOAL RESULTS:\n{combined_input}"
                f"{missing_note}\n\n"
                "Reply with JSON:\n"
                '{"synthesis": "<coherent combined answer addressing the original goal>"}\n\n'
                "Combine the sub-results into a single flowing answer. "
                "Do not just concatenate — synthesize into a coherent narrative."
            )

            result = call_llm_json(prompt, max_tokens=1500)
            return str(result.get("synthesis", ""))

        except Exception as exc:
            logger.warning("LLM merge failed: %s", exc)
            # Fallback: structured concatenation
            merged = f"# {parent_goal}\n\n" + "\n\n---\n\n".join(result_parts)
            if missing:
                merged += "\n\n**Incomplete sub-goals:**\n" + "\n".join(f"- {m}" for m in missing)
            return merged
