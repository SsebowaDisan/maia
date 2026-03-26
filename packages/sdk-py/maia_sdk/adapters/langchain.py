"""LangChain adapter — re-exported from connector-adapters for convenience."""
try:
    from maia_acp.adapters.langchain import ACPLangChainAdapter
except ImportError:
    # Inline fallback so the SDK works without the connector-adapters package
    import sys
    import os
    _adapters_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "connector-adapters", "langchain",
    )
    if os.path.isdir(_adapters_path):
        sys.path.insert(0, _adapters_path)
        from adapter import ACPLangChainAdapter  # type: ignore[import-untyped]
    else:
        raise ImportError(
            "LangChain adapter not found. Install with: pip install maia-sdk[langchain]"
        )

__all__ = ["ACPLangChainAdapter"]
