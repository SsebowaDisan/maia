"""Compatibility shim for chat page composition.

Deprecated module path for implementation details:
- use `ktem.pages.chat.chat_page` for new code.
"""

from .chat_page import ChatPage

__all__ = ["ChatPage"]
