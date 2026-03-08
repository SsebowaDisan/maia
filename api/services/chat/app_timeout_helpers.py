from __future__ import annotations

from typing import Callable


def resolve_chat_timeout_seconds(
    *,
    requested_mode: str,
    flowsettings_obj: object,
    default_model_looks_local_ollama_fn: Callable[[], bool],
    deep_search_mode: str,
) -> int:
    timeout_seconds = max(
        10,
        int(getattr(flowsettings_obj, "KH_CHAT_TIMEOUT_SECONDS", 45) or 45),
    )
    mode = str(requested_mode or "").strip().lower()
    if mode == deep_search_mode:
        timeout_seconds = max(
            timeout_seconds,
            int(getattr(flowsettings_obj, "KH_CHAT_TIMEOUT_SECONDS_DEEP_SEARCH", 600) or 600),
        )
    elif mode == "company_agent":
        timeout_seconds = max(
            timeout_seconds,
            int(getattr(flowsettings_obj, "KH_CHAT_TIMEOUT_SECONDS_COMPANY_AGENT", 300) or 300),
        )
    if default_model_looks_local_ollama_fn():
        local_timeout = int(
            getattr(flowsettings_obj, "KH_CHAT_TIMEOUT_SECONDS_LOCAL_OLLAMA", 180) or 180
        )
        timeout_seconds = max(timeout_seconds, local_timeout)
    return timeout_seconds
