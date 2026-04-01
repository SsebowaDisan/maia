"""Compat shims for legacy citation helpers.

The richer citation pipeline was removed, but many call-sites still invoke these
helpers with keyword arguments (`answer=...`, `answer_text=...`). Returning an
empty string for kwargs-only calls causes blank assistant messages.
"""

from __future__ import annotations

from typing import Any


def _passthrough_text(*args: Any, **kwargs: Any) -> str:
    if args:
        return str(args[0] or "")
    for key in ("answer", "answer_text", "text", "value"):
        if key in kwargs:
            return str(kwargs.get(key) or "")
    return ""


def enforce_required_citations(*args: Any, **kwargs: Any) -> str:
    return _passthrough_text(*args, **kwargs)


def append_required_citation_suffix(*args: Any, **kwargs: Any) -> str:
    return _passthrough_text(*args, **kwargs)


def normalize_fast_answer(*args: Any, **kwargs: Any) -> str:
    return _passthrough_text(*args, **kwargs)
