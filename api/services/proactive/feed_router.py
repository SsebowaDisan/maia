"""P5-03 — Feed router.

Responsibility: aggregate SignalEvent objects, optionally run an LLM summary
pass, then persist each signal as an InsightRecord in the insight store.
"""
from __future__ import annotations

import logging
from typing import Any

from .signal_detector import SignalEvent
from .insight_store import InsightRecord, save_insight

logger = logging.getLogger(__name__)


def _llm_enrich(signal: SignalEvent) -> str:
    """Return an LLM-generated 1-2 sentence summary for the signal.

    Falls back to signal.summary if the LLM call fails or is unavailable.
    """
    try:
        from api.services.agents.runner import run_agent_task
        prompt = (
            f"You are a business intelligence assistant. "
            f"Write a concise 1-2 sentence insight for this signal. "
            f"Signal type: {signal.signal_type}. "
            f"Title: {signal.title}. "
            f"Details: {signal.summary}"
        )
        parts: list[str] = []
        for chunk in run_agent_task(
            prompt,
            tenant_id=signal.tenant_id,
            agent_mode="ask",
        ):
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                parts.append(str(text))
        enriched = "".join(parts).strip()
        return enriched if enriched else signal.summary
    except Exception as exc:
        logger.debug("LLM enrichment failed for signal %s: %s", signal.id, exc)
        return signal.summary


def route_signal(signal: SignalEvent, *, enrich: bool = False) -> InsightRecord:
    """Persist one signal as an insight record.

    Args:
        signal: The signal event to persist.
        enrich: When True, run an LLM summary pass to improve the summary text.
    """
    summary = _llm_enrich(signal) if enrich else signal.summary
    return save_insight(
        signal.tenant_id,
        signal_type=signal.signal_type,
        severity=signal.severity,
        title=signal.title,
        summary=summary,
        source_ref=signal.source_ref,
        payload=signal.payload,
    )


def process_signals(
    signals: list[SignalEvent],
    *,
    enrich: bool = False,
) -> list[InsightRecord]:
    """Persist a batch of signals as insight records."""
    records: list[InsightRecord] = []
    for signal in signals:
        try:
            records.append(route_signal(signal, enrich=enrich))
        except Exception as exc:
            logger.error("Failed to route signal %s: %s", signal.id, exc)
    return records
