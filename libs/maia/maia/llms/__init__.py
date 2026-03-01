from __future__ import annotations

from importlib import import_module

__all__ = [
    "BaseLLM",
    # chat-specific components
    "ChatLLM",
    "EndpointChatLLM",
    "BaseMessage",
    "HumanMessage",
    "AIMessage",
    "SystemMessage",
    "AzureChatOpenAI",
    "ChatOpenAI",
    "StructuredOutputChatOpenAI",
    "LCAnthropicChat",
    "LCGeminiChat",
    "LCCohereChat",
    "LCOllamaChat",
    "LCAzureChatOpenAI",
    "LCChatOpenAI",
    "LlamaCppChat",
    # completion-specific components
    "LLM",
    "OpenAI",
    "AzureOpenAI",
    "LlamaCpp",
    # prompt-specific components
    "BasePromptComponent",
    "PromptTemplate",
    # strategies
    "SimpleLinearPipeline",
    "GatedLinearPipeline",
    "SimpleBranchingPipeline",
    "GatedBranchingPipeline",
    # chain-of-thoughts
    "ManualSequentialChainOfThought",
    "Thought",
]

_EXPORTS = {
    "BaseLLM": (".base", "BaseLLM"),
    "ChatLLM": (".chats", "ChatLLM"),
    "EndpointChatLLM": (".chats", "EndpointChatLLM"),
    "BaseMessage": ("maia.base.schema", "BaseMessage"),
    "HumanMessage": ("maia.base.schema", "HumanMessage"),
    "AIMessage": ("maia.base.schema", "AIMessage"),
    "SystemMessage": ("maia.base.schema", "SystemMessage"),
    "AzureChatOpenAI": (".chats", "AzureChatOpenAI"),
    "ChatOpenAI": (".chats", "ChatOpenAI"),
    "StructuredOutputChatOpenAI": (".chats", "StructuredOutputChatOpenAI"),
    "LCAnthropicChat": (".chats", "LCAnthropicChat"),
    "LCGeminiChat": (".chats", "LCGeminiChat"),
    "LCCohereChat": (".chats", "LCCohereChat"),
    "LCOllamaChat": (".chats", "LCOllamaChat"),
    "LCAzureChatOpenAI": (".chats", "LCAzureChatOpenAI"),
    "LCChatOpenAI": (".chats", "LCChatOpenAI"),
    "LlamaCppChat": (".chats", "LlamaCppChat"),
    "LLM": (".completions", "LLM"),
    "OpenAI": (".completions", "OpenAI"),
    "AzureOpenAI": (".completions", "AzureOpenAI"),
    "LlamaCpp": (".completions", "LlamaCpp"),
    "BasePromptComponent": (".prompts", "BasePromptComponent"),
    "PromptTemplate": (".prompts", "PromptTemplate"),
    "SimpleLinearPipeline": (".linear", "SimpleLinearPipeline"),
    "GatedLinearPipeline": (".linear", "GatedLinearPipeline"),
    "SimpleBranchingPipeline": (".branching", "SimpleBranchingPipeline"),
    "GatedBranchingPipeline": (".branching", "GatedBranchingPipeline"),
    "ManualSequentialChainOfThought": (".cot", "ManualSequentialChainOfThought"),
    "Thought": (".cot", "Thought"),
}


def __getattr__(name: str):
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = import_module(module_name, __name__) if module_name.startswith(".") else import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
