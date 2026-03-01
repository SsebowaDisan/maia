"""Package bootstrap for Maia.

Keep import-time work minimal: set telemetry flags and patch already-loaded
modules without importing heavy optional dependencies.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def _patch_posthog_if_loaded() -> None:
    posthog_module = sys.modules.get("posthog")
    if posthog_module is None:
        return

    def capture(*args, **kwargs):
        logger.info("posthog.capture called with args: %s, kwargs: %s", args, kwargs)

    posthog_module.capture = capture


def _disable_haystack_telemetry_if_loaded() -> None:
    telemetry_module = sys.modules.get("haystack.telemetry")
    if telemetry_module is None:
        return

    telemetry_module.telemetry = None


os.environ["HAYSTACK_TELEMETRY_ENABLED"] = "False"
_patch_posthog_if_loaded()
_disable_haystack_telemetry_if_loaded()
