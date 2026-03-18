"""Tool composition — automatically chain tools for complex operations.

Innovation #9 (tool composition aspect): detects when a single step should be
decomposed into a chain of tools, and provides known-good tool sequences for
common domains.

Example: "search for X" might decompose into:
  web_research → extract_content → summarize
with automatic param injection between steps.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from api.services.agent.llm_runtime import call_json_response

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompositionPlan:
    """A planned chain of tools that replaces a single step."""
    steps: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""


# Known-good tool chains for common domains.
# Each chain is a list of tool_id sequences with param-forwarding rules.
_KNOWN_CHAINS: dict[str, list[dict[str, Any]]] = {
    "marketing_research": [
        {
            "name": "deep_web_research",
            "description": "Web research with content extraction and summarization",
            "chain": ["marketing.web_research", "web.extract.structured"],
            "param_flow": {
                "marketing.web_research": {"forward_keys": ["url", "urls"]},
                "web.extract.structured": {"receive_from_previous": ["url"]},
            },
        },
        {
            "name": "competitive_scan",
            "description": "Multi-source competitive intelligence gathering",
            "chain": ["marketing.web_research", "browser.playwright.inspect"],
            "param_flow": {
                "marketing.web_research": {"forward_keys": ["url"]},
                "browser.playwright.inspect": {"receive_from_previous": ["url"]},
            },
        },
    ],
    "document_ops": [
        {
            "name": "research_to_doc",
            "description": "Research a topic and create a document",
            "chain": ["marketing.web_research", "workspace.docs.create"],
            "param_flow": {
                "marketing.web_research": {"forward_keys": ["summary", "content"]},
                "workspace.docs.create": {"receive_from_previous": ["content"]},
            },
        },
    ],
    "data_analysis": [
        {
            "name": "extract_and_analyze",
            "description": "Extract structured data and load into sheet",
            "chain": ["web.extract.structured", "workspace.sheets.update"],
            "param_flow": {
                "web.extract.structured": {"forward_keys": ["data", "rows"]},
                "workspace.sheets.update": {"receive_from_previous": ["values"]},
            },
        },
    ],
}

_DETECT_SYSTEM_PROMPT = """\
You are a tool composition advisor for an AI agent.
You detect when a single planned step would be more effective as a chain
of 2-3 tool calls, where each subsequent tool uses output from the previous.

Rules:
- Return ONLY valid JSON — no prose, no markdown.
- Only recommend composition when it clearly adds value (e.g., the step
  implicitly requires multiple capabilities).
- Do not decompose steps that are already simple, single-purpose tool calls.
- Use only tool IDs from the available list.
- Each step in the chain needs tool_id, title, params, why_this_step,
  expected_evidence, and receives_from_previous (list of param keys to
  auto-inject from the previous step's output).
"""

_DETECT_USER_TEMPLATE = """\
CURRENT STEP:
  tool_id: {tool_id}
  title: {step_title}
  params: {step_params}
  why: {why_this_step}

AVAILABLE TOOLS:
  {available_tools}

EVIDENCE SO FAR:
{evidence_pool}

Should this step be decomposed into a chain of tools?
If yes, provide the chain.  If no, return {{"should_compose": false}}.

Return JSON:
{{
  "should_compose": <bool>,
  "rationale": "<why composition helps or why it doesn't>",
  "chain": [
    {{
      "tool_id": "<tool_id>",
      "title": "<short title>",
      "params": {{}},
      "why_this_step": "<purpose in the chain>",
      "expected_evidence": ["<what this finds>"],
      "receives_from_previous": ["<param keys auto-injected>"]
    }}
  ]
}}
"""


def _format_evidence(evidence_pool: list[str]) -> str:
    if not evidence_pool:
        return "  (no evidence collected yet)"
    return "\n".join(f"  - {e[:200]}" for e in evidence_pool[-6:])


class ToolComposer:
    """Detects tool composition opportunities and builds tool chains.

    Automatically decomposes complex single-step operations into
    multi-tool chains with param forwarding between steps.
    """

    def detect_composition_opportunity(
        self,
        step: dict[str, Any],
        available_tools: list[str],
        evidence_pool: list[str],
    ) -> CompositionPlan | None:
        """Detect when a step should be decomposed into a tool chain.

        Parameters
        ----------
        step:
            Dict with tool_id, title, params, why_this_step.
        available_tools:
            List of available tool IDs.
        evidence_pool:
            Accumulated evidence from prior steps.

        Returns
        -------
        CompositionPlan if decomposition is beneficial, None otherwise.
        """
        import json

        tool_id = str(step.get("tool_id", ""))
        step_title = str(step.get("title", ""))
        step_params = step.get("params", {})
        why = str(step.get("why_this_step", ""))

        prompt = _DETECT_USER_TEMPLATE.format(
            tool_id=tool_id,
            step_title=step_title[:120],
            step_params=json.dumps(step_params, default=str)[:300],
            why_this_step=why[:200],
            available_tools=", ".join(available_tools[:30]),
            evidence_pool=_format_evidence(evidence_pool),
        )

        try:
            raw = call_json_response(
                system_prompt=_DETECT_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.15,
                timeout_seconds=12,
            )
        except Exception as exc:
            logger.debug("tool_composer.detect_failed error=%s", exc)
            return None

        if not isinstance(raw, dict):
            return None

        if not raw.get("should_compose", False):
            return None

        chain_raw = raw.get("chain", [])
        if not isinstance(chain_raw, list) or len(chain_raw) < 2:
            return None

        # Validate chain: all tool_ids must be in available_tools
        chain_steps: list[dict[str, Any]] = []
        available_set = set(available_tools)
        for item in chain_raw[:4]:
            if not isinstance(item, dict):
                continue
            chain_tool_id = str(item.get("tool_id", "")).strip()
            if not chain_tool_id or chain_tool_id not in available_set:
                continue
            chain_steps.append({
                "tool_id": chain_tool_id,
                "title": str(item.get("title", ""))[:120],
                "params": item.get("params") if isinstance(item.get("params"), dict) else {},
                "why_this_step": str(item.get("why_this_step", ""))[:200],
                "expected_evidence": tuple(
                    str(e) for e in (item.get("expected_evidence") or [])[:4]
                ),
                "receives_from_previous": list(
                    str(k) for k in (item.get("receives_from_previous") or [])[:6]
                ),
            })

        if len(chain_steps) < 2:
            return None

        rationale = str(raw.get("rationale", ""))[:300]
        return CompositionPlan(steps=chain_steps, rationale=rationale)

    def compose_tool_chain(
        self,
        tools: list[str],
        initial_params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build a tool chain with auto-param-injection between steps.

        Parameters
        ----------
        tools:
            Ordered list of tool IDs to chain.
        initial_params:
            Parameters for the first tool in the chain.

        Returns
        -------
        List of step dicts, each with tool_id, title, params, why_this_step.
        Subsequent steps include a __previous_output_keys marker for the
        executor to inject results from the prior step.
        """
        if not tools:
            return []

        chain: list[dict[str, Any]] = []
        for i, tool_id in enumerate(tools):
            step: dict[str, Any] = {
                "tool_id": tool_id,
                "title": f"Chain step {i + 1}: {tool_id}",
                "params": dict(initial_params) if i == 0 else {},
                "why_this_step": (
                    f"Step {i + 1} of {len(tools)} in composed chain."
                ),
                "expected_evidence": (),
            }
            if i > 0:
                # Mark that this step should receive output from the previous
                step["params"]["__chain_inject_from_previous"] = True
                step["params"]["__chain_position"] = i
            chain.append(step)

        return chain

    def get_recommended_chains(
        self,
        domain: str,
    ) -> list[dict[str, Any]]:
        """Return known-good tool sequences for a domain.

        Parameters
        ----------
        domain:
            The capability domain (e.g., "marketing_research", "document_ops").

        Returns
        -------
        List of chain definitions with name, description, tool sequence,
        and param flow rules.
        """
        chains = _KNOWN_CHAINS.get(domain, [])
        return list(chains)
