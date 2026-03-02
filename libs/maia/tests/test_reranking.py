from unittest.mock import patch

import pytest
from openai.types.chat.chat_completion import ChatCompletion

from maia.base import Document
from maia.indices.rankings import LLMReranking
from maia.llms import AzureChatOpenAI


def reranking_responses():
    return [
        ChatCompletion.parse_obj(
            {
                "id": "chatcmpl-7qyuw6Q1CFCpcKsMdFkmUPUa7JP2x",
                "object": "chat.completion",
                "created": 1692338378,
                "model": "gpt-35-turbo",
                "system_fingerprint": None,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": text,
                            "function_call": None,
                            "tool_calls": None,
                        },
                        "logprobs": None,
                    }
                ],
                "usage": {
                    "completion_tokens": 9,
                    "prompt_tokens": 10,
                    "total_tokens": 19,
                },
            }
        )
        for text in ["YES", "NO", "YES"]
    ]


@pytest.fixture
def llm():
    return AzureChatOpenAI(
        api_key="dummy",
        api_version="2024-05-01-preview",
        azure_deployment="gpt-4o",
        azure_endpoint="https://test.openai.azure.com/",
    )


def test_reranking(llm):
    documents = [Document(text=f"test {idx}") for idx in range(3)]
    query = "test query"

    reranker = LLMReranking(llm=llm, concurrent=False)
    with patch(
        "openai.resources.chat.completions.Completions.create",
        side_effect=reranking_responses(),
    ) as openai_completion:
        rerank_docs = reranker(documents, query=query)

    openai_completion.assert_called()
    assert len(rerank_docs) == 2
