"""Compatibility shim for Playwright contact form connector.

Deprecated module path for implementation details:
- use `api.services.agent.connectors.browser_contact` for new code.
"""

from .browser_contact import BrowserContactConnector

__all__ = ["BrowserContactConnector"]
