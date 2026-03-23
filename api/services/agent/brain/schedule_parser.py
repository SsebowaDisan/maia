"""Schedule Parser — LLM-based natural language to cron conversion.

Parses time references like "every Monday at 9am" into cron expressions.
Uses LLM for understanding, not regex pattern matching.
"""
from __future__ import annotations

import json
import logging
import os
import concurrent.futures
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You extract schedule information from text.

Respond with valid JSON only:
{
  "detected": true | false,
  "cron": "cron expression (5 fields: minute hour day month weekday)",
  "description": "human-readable description like 'Every Monday at 09:00'",
  "time": "HH:MM",
  "timezone": "timezone or UTC if not mentioned"
}

Examples:
- "every Monday" → {"detected": true, "cron": "0 9 * * 1", "description": "Every Monday at 09:00", "time": "09:00", "timezone": "UTC"}
- "daily at 3pm" → {"detected": true, "cron": "0 15 * * *", "description": "Every day at 15:00", "time": "15:00", "timezone": "UTC"}
- "analyse our revenue" → {"detected": false, "cron": "", "description": "", "time": "", "timezone": ""}

If no time is mentioned but a schedule is implied, default to 09:00.
If no timezone is mentioned, use UTC."""


def parse_schedule(text: str, tenant_id: str = "") -> dict[str, Any]:
    """Parse natural language text for schedule information using LLM."""
    if not text or len(text) < 5:
        return {"detected": False, "cron": "", "description": "", "time": "", "timezone": "UTC"}

    try:
        from api.services.agent.llm_runtime import call_json_response

        timeout_seconds = _schedule_timeout_seconds()
        payload = call_json_response(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=f"Extract any schedule or timing information from this text:\n\n{text[:500]}",
            timeout_seconds=max(4, int(timeout_seconds)),
            max_tokens=220,
            retries=1,
            allow_json_repair=True,
            enable_thinking=False,
            use_fallback_models=False,
        )
        if isinstance(payload, dict):
            return _normalize_payload(payload)
    except Exception as exc:
        logger.debug("Schedule parse direct LLM call failed: %s", exc)

    # Fallback path for environments where direct JSON runtime is unavailable.
    timeout_seconds = _schedule_timeout_seconds()
    raw = _call_llm_via_runner(text=text, tenant_id=tenant_id, timeout_seconds=timeout_seconds)
    if not raw:
        return {"detected": False, "cron": "", "description": "", "time": "", "timezone": "UTC"}
    return _parse_response(raw)


def _call_llm_via_runner(*, text: str, tenant_id: str, timeout_seconds: float) -> str:
    try:
        from api.services.agents.runner import run_agent_task

        def _run() -> str:
            parts: list[str] = []
            for chunk in run_agent_task(
                f"Extract any schedule or timing information from this text:\n\n{text[:500]}",
                tenant_id=tenant_id,
                system_prompt=_SYSTEM_PROMPT,
                agent_mode="ask",
                max_tool_calls=0,
            ):
                t = chunk.get("text") or chunk.get("content") or ""
                if t:
                    parts.append(str(t))
            return "".join(parts)

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(_run)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            future.cancel()
            logger.warning("Schedule parser fallback timed out after %.1fs", timeout_seconds)
            return ""
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    except Exception as exc:
        logger.debug("Schedule parse fallback runner call failed: %s", exc)
        return ""


def _parse_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        for i in range(len(text)):
            if text[i] == "{":
                for j in range(len(text) - 1, i, -1):
                    if text[j] == "}":
                        try:
                            parsed = json.loads(text[i:j + 1])
                            break
                        except json.JSONDecodeError:
                            continue
                else:
                    continue
                break
        else:
            return {"detected": False, "cron": "", "description": "", "time": "", "timezone": "UTC"}

    if not isinstance(parsed, dict):
        return {"detected": False, "cron": "", "description": "", "time": "", "timezone": "UTC"}
    return _normalize_payload(parsed)


def _normalize_payload(parsed: dict[str, Any]) -> dict[str, Any]:
    detected = bool(parsed.get("detected"))
    cron = str(parsed.get("cron", "")).strip()
    # Validate cron has 5 fields
    if detected and len(cron.split()) != 5:
        detected = False

    return {
        "detected": detected,
        "cron": cron if detected else "",
        "description": str(parsed.get("description", "")).strip(),
        "time": str(parsed.get("time", "")).strip(),
        "timezone": str(parsed.get("timezone", "UTC")).strip() or "UTC",
    }


def _schedule_timeout_seconds() -> float:
    try:
        value = float(os.getenv("MAIA_SCHEDULE_PARSE_TIMEOUT_SECONDS", "8"))
    except Exception:
        value = 8.0
    # Keep schedule parsing cheap so it never blocks assembly for long.
    if value < 2:
        return 2.0
    if value > 30:
        return 30.0
    return value
