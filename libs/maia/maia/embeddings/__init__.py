from __future__ import annotations

from importlib import import_module

__all__ = [
    "BaseEmbeddings",
    "EndpointEmbeddings",
    "TeiEndpointEmbeddings",
    "LCOpenAIEmbeddings",
    "LCAzureOpenAIEmbeddings",
    "LCCohereEmbeddings",
    "LCHuggingFaceEmbeddings",
    "LCGoogleEmbeddings",
    "LCMistralEmbeddings",
    "OpenAIEmbeddings",
    "AzureOpenAIEmbeddings",
    "FastEmbedEmbeddings",
    "VoyageAIEmbeddings",
]

_EXPORTS = {
    "BaseEmbeddings": (".base", "BaseEmbeddings"),
    "EndpointEmbeddings": (".endpoint_based", "EndpointEmbeddings"),
    "TeiEndpointEmbeddings": (".tei_endpoint_embed", "TeiEndpointEmbeddings"),
    "LCOpenAIEmbeddings": (".langchain_based", "LCOpenAIEmbeddings"),
    "LCAzureOpenAIEmbeddings": (".langchain_based", "LCAzureOpenAIEmbeddings"),
    "LCCohereEmbeddings": (".langchain_based", "LCCohereEmbeddings"),
    "LCHuggingFaceEmbeddings": (".langchain_based", "LCHuggingFaceEmbeddings"),
    "LCGoogleEmbeddings": (".langchain_based", "LCGoogleEmbeddings"),
    "LCMistralEmbeddings": (".langchain_based", "LCMistralEmbeddings"),
    "OpenAIEmbeddings": (".openai", "OpenAIEmbeddings"),
    "AzureOpenAIEmbeddings": (".openai", "AzureOpenAIEmbeddings"),
    "FastEmbedEmbeddings": (".fastembed", "FastEmbedEmbeddings"),
    "VoyageAIEmbeddings": (".voyageai", "VoyageAIEmbeddings"),
}


def __getattr__(name: str):
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
