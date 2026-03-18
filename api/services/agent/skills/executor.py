"""Skill executor — runs a skill pack within an agent context."""
from __future__ import annotations

import logging
from typing import Any

from .loader import SkillPack

logger = logging.getLogger(__name__)


class SkillExecutor:
    """Executes a skill pack by composing its prompt, tools, and config
    into an agent execution context.

    This is the bridge between the skill-pack format and Maia's agent runner.
    """

    def __init__(self, skill: SkillPack) -> None:
        self._skill = skill

    @property
    def skill(self) -> SkillPack:
        return self._skill

    def build_system_prompt(self, *, base_prompt: str = "", context: str = "") -> str:
        """Compose the full system prompt by layering skill instructions."""
        parts: list[str] = []

        if base_prompt:
            parts.append(base_prompt)

        parts.append(f"## Skill: {self._skill.name}")
        if self._skill.description:
            parts.append(self._skill.description)

        if self._skill.prompt:
            parts.append("## Instructions")
            parts.append(self._skill.prompt)

        if context:
            parts.append("## Context")
            parts.append(context)

        if self._skill.example_inputs:
            parts.append("## Example Inputs")
            for i, ex in enumerate(self._skill.example_inputs[:3], 1):
                parts.append(f"**Example {i}:**")
                if isinstance(ex, dict):
                    for k, v in ex.items():
                        parts.append(f"- {k}: {v}")
                else:
                    parts.append(str(ex))

        return "\n\n".join(parts)

    def build_tool_list(self, available_tools: list[str] | None = None) -> list[str]:
        """Return the list of tool IDs this skill needs.

        If available_tools is provided, only return tools that are actually available.
        Logs warnings for missing required tools.
        """
        needed = list(self._skill.required_tools)
        if available_tools is None:
            return needed

        available_set = set(available_tools)
        resolved: list[str] = []
        for tool_id in needed:
            if tool_id in available_set:
                resolved.append(tool_id)
            else:
                logger.warning(
                    "Skill %s requires tool %s but it is not available",
                    self._skill.name,
                    tool_id,
                )
        return resolved

    def build_run_config(self) -> dict[str, Any]:
        """Build agent run configuration overrides from the skill pack."""
        config: dict[str, Any] = {}

        if self._skill.model:
            config["model"] = self._skill.model
        if self._skill.temperature is not None:
            config["temperature"] = self._skill.temperature
        if self._skill.max_tokens is not None:
            config["max_tokens"] = self._skill.max_tokens
        if self._skill.required_connectors:
            config["required_connectors"] = self._skill.required_connectors
        if self._skill.mcp_servers:
            config["mcp_servers"] = self._skill.mcp_servers

        return config

    def validate(self, available_tools: list[str] | None = None) -> list[str]:
        """Validate the skill pack. Returns list of warning messages (empty = ok)."""
        warnings: list[str] = []

        if not self._skill.name:
            warnings.append("Skill has no name")
        if not self._skill.prompt:
            warnings.append("Skill has no prompt/instructions")
        if available_tools is not None:
            available_set = set(available_tools)
            for tool_id in self._skill.required_tools:
                if tool_id not in available_set:
                    warnings.append(f"Required tool '{tool_id}' is not available")

        return warnings
