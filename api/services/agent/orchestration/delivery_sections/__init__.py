from __future__ import annotations

from typing import Any


def maybe_send_server_delivery(*args: Any, **kwargs: Any):
    from .app import maybe_send_server_delivery as _maybe_send_server_delivery

    return _maybe_send_server_delivery(*args, **kwargs)

__all__ = ["maybe_send_server_delivery"]
