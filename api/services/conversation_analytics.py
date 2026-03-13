"""Conversation analytics service.

Reads persisted ``message_meta`` perf records and assembles aggregated
analytics suitable for the ``GET /api/conversations/{id}/analytics`` endpoint.

All computation is done server-side; no client-side aggregation is needed.
"""
from __future__ import annotations

from typing import Any


def build_analytics_response(
    conversation_id: str,
    data_source: dict[str, Any],
) -> dict[str, Any]:
    """Assemble analytics from the conversation's message_meta perf records.

    Parameters
    ----------
    conversation_id:
        ID of the conversation being analysed.
    data_source:
        The raw data_source dict as returned by the conversation store
        (contains ``message_meta``, ``messages``, etc.).

    Returns
    -------
    dict with keys:
        conversation_id, turn_count, turns, aggregates
    """
    message_meta: list[dict[str, Any]] = data_source.get("message_meta") or []

    turn_records: list[dict[str, Any]] = []
    for idx, meta in enumerate(message_meta):
        perf = meta.get("perf") or {}
        turn_records.append(
            {
                "turn_index": idx,
                "mode_requested": perf.get("mode_requested") or meta.get("mode") or "ask",
                "mode_actually_used": perf.get("mode_actually_used") or meta.get("mode_actually_used") or "ask",
                "halt_reason": perf.get("halt_reason") or meta.get("halt_reason"),
                "snippets_retrieved": perf.get("snippets_retrieved"),
                "snippets_sent_to_llm": perf.get("snippets_sent_to_llm"),
                "snippets_cited": perf.get("snippets_cited"),
                "retrieval_score_avg": perf.get("retrieval_score_avg"),
                "context_tokens_used": perf.get("context_tokens_used"),
                "context_tokens_budget": perf.get("context_tokens_budget"),
                "mindmap_generated": bool(perf.get("mindmap_generated")),
                "focus_applied": bool(perf.get("focus_applied")),
                "retrieval_ms": perf.get("retrieval_ms"),
                "llm_ms": perf.get("llm_ms"),
                "total_turn_ms": perf.get("total_turn_ms"),
            }
        )

    aggregates = _compute_aggregates(turn_records)

    return {
        "conversation_id": conversation_id,
        "turn_count": len(turn_records),
        "turns": turn_records,
        "aggregates": aggregates,
    }


def _compute_aggregates(turns: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics across all turns."""
    scores = [t["retrieval_score_avg"] for t in turns if t["retrieval_score_avg"] is not None]
    retrieval_score_avg = round(sum(scores) / len(scores), 4) if scores else None

    cited = [t["snippets_cited"] for t in turns if t["snippets_cited"] is not None]
    sent = [t["snippets_sent_to_llm"] for t in turns if t["snippets_sent_to_llm"] is not None]
    if cited and sent and len(cited) == len(sent):
        citation_pairs = [(c, s) for c, s in zip(cited, sent) if s and s > 0]
        citation_rate_avg = round(
            sum(c / s for c, s in citation_pairs) / len(citation_pairs), 4
        ) if citation_pairs else None
    else:
        citation_rate_avg = None

    halt_reasons = [t["halt_reason"] for t in turns if t["halt_reason"]]
    fallback_rate = round(len(halt_reasons) / len(turns), 4) if turns else 0.0

    mode_distribution: dict[str, int] = {}
    for t in turns:
        mode = str(t["mode_actually_used"] or "ask")
        mode_distribution[mode] = mode_distribution.get(mode, 0) + 1

    budget_pairs = [
        (t["context_tokens_used"], t["context_tokens_budget"])
        for t in turns
        if t["context_tokens_used"] is not None and t["context_tokens_budget"]
    ]
    context_budget_utilisation_avg = (
        round(
            sum(u / b for u, b in budget_pairs if b > 0) / len(budget_pairs), 4
        )
        if budget_pairs
        else None
    )

    return {
        "retrieval_score_avg": retrieval_score_avg,
        "citation_rate_avg": citation_rate_avg,
        "fallback_rate": fallback_rate,
        "fallback_count": len(halt_reasons),
        "mode_distribution": mode_distribution,
        "context_budget_utilisation_avg": context_budget_utilisation_avg,
    }
