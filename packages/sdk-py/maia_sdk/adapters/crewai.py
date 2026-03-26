"""CrewAI adapter — re-exported from connector-adapters for convenience."""
try:
    from maia_acp.adapters.crewai import ACPCrewAIAdapter
except ImportError:
    import sys
    import os
    _adapters_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "connector-adapters", "crewai",
    )
    if os.path.isdir(_adapters_path):
        sys.path.insert(0, _adapters_path)
        from adapter import ACPCrewAIAdapter  # type: ignore[import-untyped]
    else:
        raise ImportError(
            "CrewAI adapter not found. Install with: pip install maia-sdk[crewai]"
        )

__all__ = ["ACPCrewAIAdapter"]
