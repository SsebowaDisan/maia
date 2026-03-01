from __future__ import annotations

from importlib import import_module

__all__ = [
    "ChatOpenAI",
    "AzureChatOpenAI",
    "ChatLLM",
    "EndpointChatLLM",
    "ChatOpenAI",
    "StructuredOutputChatOpenAI",
    "LCAnthropicChat",
    "LCGeminiChat",
    "LCCohereChat",
    "LCOllamaChat",
    "LCChatOpenAI",
    "LCAzureChatOpenAI",
    "LCChatMixin",
    "LlamaCppChat",
]

_EXPORTS = {
    "ChatLLM": (".base", "ChatLLM"),
    "EndpointChatLLM": (".endpoint_based", "EndpointChatLLM"),
    "LCAnthropicChat": (".langchain_based", "LCAnthropicChat"),
    "LCAzureChatOpenAI": (".langchain_based", "LCAzureChatOpenAI"),
    "LCChatMixin": (".langchain_based", "LCChatMixin"),
    "LCChatOpenAI": (".langchain_based", "LCChatOpenAI"),
    "LCCohereChat": (".langchain_based", "LCCohereChat"),
    "LCGeminiChat": (".langchain_based", "LCGeminiChat"),
    "LCOllamaChat": (".langchain_based", "LCOllamaChat"),
    "LlamaCppChat": (".llamacpp", "LlamaCppChat"),
    "AzureChatOpenAI": (".openai", "AzureChatOpenAI"),
    "ChatOpenAI": (".openai", "ChatOpenAI"),
    "StructuredOutputChatOpenAI": (".openai", "StructuredOutputChatOpenAI"),
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
