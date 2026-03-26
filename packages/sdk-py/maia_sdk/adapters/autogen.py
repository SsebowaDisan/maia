"""AutoGen adapter — re-exported from connector-adapters for convenience."""
try:
    from maia_acp.adapters.autogen import ACPAutoGenAdapter
except ImportError:
    import sys
    import os
    _adapters_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "connector-adapters", "autogen",
    )
    if os.path.isdir(_adapters_path):
        sys.path.insert(0, _adapters_path)
        from adapter import ACPAutoGenAdapter  # type: ignore[import-untyped]
    else:
        raise ImportError(
            "AutoGen adapter not found. Install with: pip install maia-sdk[autogen]"
        )

__all__ = ["ACPAutoGenAdapter"]
