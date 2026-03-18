"""Innovation #9 — Multi-Agent Consensus Engine.

Dispatches the same task to multiple agents in parallel, collects their
proposals, and uses LLM evaluation to determine consensus or synthesise
the best answer from multiple perspectives.
"""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class AgentProposal:
    """A single agent's response to a consensus task."""
    agent_id: str
    response: str
    confidence: float  # 0.0–1.0
    evidence_refs: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class ConsensusResult:
    """Outcome of evaluating multiple agent proposals."""
    winning_proposal: AgentProposal
    consensus_type: str  # "unanimous" | "majority" | "synthesized" | "no_consensus"
    agreement_score: float  # 0.0–1.0
    dissenting_views: list[str] = field(default_factory=list)
    synthesis: str = ""


# ── Engine ────────────────────────────────────────────────────────────────────

class ConsensusEngine:
    """Gather proposals from multiple agents, evaluate consensus, and arbitrate."""

    def __init__(
        self,
        *,
        tenant_id: str,
        run_id: str | None = None,
        max_workers: int = 4,
        on_event: Optional[Callable[[dict[str, Any]], None]] = None,
    ):
        self.tenant_id = tenant_id
        self.run_id = run_id or str(uuid.uuid4())
        self.max_workers = max_workers
        self.on_event = on_event

    # ── Public API ────────────────────────────────────────────────────────

    def gather_proposals(
        self,
        task: str,
        agent_ids: list[str],
        context: dict[str, Any] | None = None,
    ) -> list[AgentProposal]:
        """Dispatch *task* to each agent in parallel and collect proposals.

        Args:
            task: Natural-language task string sent to every agent.
            agent_ids: List of agent IDs to query.
            context: Optional shared context dict injected into each agent.

        Returns:
            List of AgentProposal objects (one per successful agent).
        """
        context = context or {}
        proposals: list[AgentProposal] = []

        self._emit({
            "event_type": "consensus.gather_start",
            "task_preview": task[:200],
            "agent_ids": agent_ids,
        })

        def _run_one(agent_id: str) -> AgentProposal:
            return self._collect_proposal(agent_id, task, context)

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(agent_ids))) as pool:
            futures = {pool.submit(_run_one, aid): aid for aid in agent_ids}
            for future in as_completed(futures):
                aid = futures[future]
                try:
                    proposals.append(future.result())
                except Exception as exc:
                    logger.warning("Agent '%s' failed during consensus gather: %s", aid, exc)
                    self._emit({
                        "event_type": "consensus.agent_failed",
                        "agent_id": aid,
                        "error": str(exc)[:300],
                    })

        self._emit({
            "event_type": "consensus.gather_done",
            "proposal_count": len(proposals),
        })
        return proposals

    def evaluate_proposals(
        self,
        proposals: list[AgentProposal],
    ) -> ConsensusResult:
        """Evaluate a set of proposals and determine consensus.

        Consensus types:
            unanimous   — all agents essentially agree
            majority    — >50% agree on the core answer
            synthesized — no clear winner; best parts combined
            no_consensus — proposals fundamentally conflict; escalate

        Returns:
            A ConsensusResult with the winning/synthesized answer.
        """
        if not proposals:
            return ConsensusResult(
                winning_proposal=AgentProposal(agent_id="none", response="", confidence=0.0),
                consensus_type="no_consensus",
                agreement_score=0.0,
                dissenting_views=["No proposals received."],
                synthesis="",
            )

        if len(proposals) == 1:
            return ConsensusResult(
                winning_proposal=proposals[0],
                consensus_type="unanimous",
                agreement_score=1.0,
                synthesis=proposals[0].response,
            )

        # Use LLM to compare proposals
        return self._llm_evaluate(proposals)

    def arbitrate(
        self,
        proposals: list[AgentProposal],
        criteria: str,
    ) -> AgentProposal:
        """When consensus fails, LLM picks the best proposal by explicit criteria.

        Args:
            proposals: The candidate proposals.
            criteria: E.g. "accuracy", "completeness", "evidence quality".

        Returns:
            The single best AgentProposal.
        """
        if not proposals:
            return AgentProposal(agent_id="none", response="", confidence=0.0)
        if len(proposals) == 1:
            return proposals[0]

        return self._llm_arbitrate(proposals, criteria)

    # ── Private helpers ───────────────────────────────────────────────────

    def _collect_proposal(
        self, agent_id: str, task: str, context: dict[str, Any]
    ) -> AgentProposal:
        """Run a single agent and wrap its output as an AgentProposal."""
        from api.services.agents.orchestrator import delegate_to_agent

        result = delegate_to_agent(
            parent_agent_id="consensus_engine",
            child_agent_id=agent_id,
            task=task,
            context=context,
            tenant_id=self.tenant_id,
            run_id=self.run_id,
            on_event=self.on_event,
        )

        if not result.get("success"):
            raise RuntimeError(
                f"Agent '{agent_id}' failed: {result.get('error', 'unknown')}"
            )

        response_text = str(result.get("result") or "")

        # Attempt to extract confidence from the response via a quick LLM call
        confidence = self._estimate_confidence(agent_id, response_text)

        return AgentProposal(
            agent_id=agent_id,
            response=response_text,
            confidence=confidence,
            reasoning=f"Agent {agent_id} responded with {len(response_text)} chars.",
        )

    def _estimate_confidence(self, agent_id: str, response: str) -> float:
        """Quick LLM call to estimate how confident the response is."""
        try:
            from api.services.agents.llm_utils import call_llm_json

            result = call_llm_json(
                f"Rate the confidence of this response on a 0.0-1.0 scale. "
                f"Consider: clarity, specificity, evidence provided, hedging language. "
                f"Reply JSON: {{\"confidence\": <float>}}\n\n"
                f"Response:\n{response[:1500]}",
                max_tokens=50,
            )
            return max(0.0, min(1.0, float(result.get("confidence", 0.5))))
        except Exception:
            return 0.5

    def _llm_evaluate(self, proposals: list[AgentProposal]) -> ConsensusResult:
        """Use LLM to compare proposals and determine consensus type."""
        from api.services.agents.llm_utils import call_llm_json

        proposal_summaries = []
        for i, p in enumerate(proposals):
            proposal_summaries.append(
                f"Proposal {i} (agent={p.agent_id}, confidence={p.confidence:.2f}):\n"
                f"{p.response[:1000]}"
            )

        prompt = (
            "You are evaluating multiple agent proposals for the same task. "
            "Compare them and determine the consensus.\n\n"
            + "\n\n---\n\n".join(proposal_summaries)
            + "\n\n"
            "Reply with JSON:\n"
            "{\n"
            '  "consensus_type": "unanimous"|"majority"|"synthesized"|"no_consensus",\n'
            '  "agreement_score": <0.0-1.0>,\n'
            '  "winning_index": <index of best proposal or -1 if synthesized>,\n'
            '  "dissenting_views": ["<summary of disagreements>"],\n'
            '  "synthesis": "<combined best answer if synthesized, else empty>"\n'
            "}\n\n"
            "Rules:\n"
            '- "unanimous": all proposals essentially say the same thing\n'
            '- "majority": >50% agree on the core point, but some disagree\n'
            '- "synthesized": proposals differ but can be combined into a better answer\n'
            '- "no_consensus": fundamental disagreement that needs human arbitration'
        )

        try:
            result = call_llm_json(prompt, max_tokens=800)
        except Exception as exc:
            logger.warning("LLM consensus evaluation failed: %s", exc)
            # Fallback: pick highest confidence
            best = max(proposals, key=lambda p: p.confidence)
            return ConsensusResult(
                winning_proposal=best,
                consensus_type="no_consensus",
                agreement_score=0.0,
                dissenting_views=["LLM evaluation failed; fell back to highest confidence."],
                synthesis=best.response,
            )

        consensus_type = str(result.get("consensus_type", "no_consensus"))
        agreement_score = max(0.0, min(1.0, float(result.get("agreement_score", 0.0))))
        winning_index = int(result.get("winning_index", 0))
        dissenting_views = [str(v) for v in result.get("dissenting_views", [])]
        synthesis = str(result.get("synthesis", ""))

        if 0 <= winning_index < len(proposals):
            winning = proposals[winning_index]
        else:
            winning = max(proposals, key=lambda p: p.confidence)

        # If synthesized, create a synthetic proposal
        if consensus_type == "synthesized" and synthesis:
            winning = AgentProposal(
                agent_id="consensus_synthesis",
                response=synthesis,
                confidence=agreement_score,
                reasoning="Synthesized from multiple agent proposals.",
            )

        return ConsensusResult(
            winning_proposal=winning,
            consensus_type=consensus_type,
            agreement_score=agreement_score,
            dissenting_views=dissenting_views,
            synthesis=synthesis or winning.response,
        )

    def _llm_arbitrate(
        self, proposals: list[AgentProposal], criteria: str
    ) -> AgentProposal:
        """LLM picks the best proposal based on explicit criteria."""
        from api.services.agents.llm_utils import call_llm_json

        proposal_summaries = []
        for i, p in enumerate(proposals):
            proposal_summaries.append(
                f"Proposal {i} (agent={p.agent_id}):\n{p.response[:1000]}"
            )

        prompt = (
            f"You are arbitrating between multiple proposals. "
            f"Pick the single best one based on these criteria: {criteria}\n\n"
            + "\n\n---\n\n".join(proposal_summaries)
            + "\n\n"
            "Reply JSON: {\"winning_index\": <int>, \"reasoning\": \"<why>\"}"
        )

        try:
            result = call_llm_json(prompt, max_tokens=300)
            idx = int(result.get("winning_index", 0))
            if 0 <= idx < len(proposals):
                winner = proposals[idx]
                winner.reasoning = str(result.get("reasoning", winner.reasoning))
                return winner
        except Exception as exc:
            logger.warning("LLM arbitration failed: %s", exc)

        # Fallback: highest confidence
        return max(proposals, key=lambda p: p.confidence)

    def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass
