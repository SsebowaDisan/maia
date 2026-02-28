"""Compatibility shim for server-side delivery orchestration.

Deprecated module path for implementation details:
- use `api.services.agent.orchestration.delivery_sections` for new code.
"""

from .delivery_sections import maybe_send_server_delivery

__all__ = ["maybe_send_server_delivery"]
