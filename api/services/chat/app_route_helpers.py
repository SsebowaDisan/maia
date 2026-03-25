from __future__ import annotations

from typing import Any, Callable


def should_auto_web_fallback(
    *,
    message: str,
    chat_history: list[list[str]],
    disable_auto_web_fallback: bool,
    call_json_response_fn: Callable[..., dict[str, Any]],
    env_bool_fn: Callable[[str, bool], bool],
) -> bool:
    if disable_auto_web_fallback:
        return False
    if not env_bool_fn("MAIA_CHAT_AUTO_WEB_FALLBACK_ENABLED", default=True):
        return False

    message_text = str(message or "").strip()
    if not message_text:
        return False

    lowered_message = message_text.lower()
    if "http://" in lowered_message or "https://" in lowered_message:
        return True

    for turn in reversed(chat_history[-5:]):
        if not isinstance(turn, list) or not turn:
            continue
        user_text = str(turn[0] or "").strip().lower()
        if "http://" in user_text or "https://" in user_text:
            return True

    try:
        router_response = call_json_response_fn(
            model=None,
            system_prompt=(
                "You route a user message to either local indexed context or live web research. "
                "Return JSON only with keys: route ('local'|'web'), confidence (0..1), reason."
            ),
            user_prompt=(
                "Message:\n"
                f"{message_text}\n\n"
                "Recent chat history (latest up to 5 turns):\n"
                f"{chat_history[-5:]}"
            ),
            max_output_tokens=220,
            temperature=0,
        )
    except Exception:
        return False

    route = str((router_response or {}).get("route") or "").strip().lower()
    confidence_raw = (router_response or {}).get("confidence", 0)
    try:
        confidence = float(confidence_raw)
    except Exception:
        confidence = 0.0
    return route == "web" and confidence >= 0.55
