from typing import List, Union

from pydantic import BaseModel, Field

from maia.base import BaseComponent
from maia.base.schema import HumanMessage, SystemMessage
from maia.llms import BaseLLM


class CitationSpan(BaseModel):
    """A cited span anchor represented by start/end phrases."""

    start_phrase: str = Field(
        ...,
        description=(
            "First 5-8 words from the relevant span, copied exactly from context."
        ),
    )
    end_phrase: str = Field(
        ...,
        description=(
            "Last 5-8 words from the relevant span, copied exactly from context."
        ),
    )


class CiteEvidence(BaseModel):
    """List of evidences (maximum 5) to support the answer."""

    evidences: List[Union[CitationSpan, str]] = Field(
        ...,
        description=(
            "Each evidence item should identify span boundaries using start_phrase "
            "and end_phrase copied exactly from context."
        ),
    )


class CitationPipeline(BaseComponent):
    """Citation pipeline to extract cited evidences from source
    (based on input question)"""

    llm: BaseLLM

    def run(self, context: str, question: str):
        return self.invoke(context, question)

    def prepare_llm(self, context: str, question: str):
        schema = CiteEvidence.schema()
        function = {
            "name": schema["title"],
            "description": schema["description"],
            "parameters": schema,
        }
        llm_kwargs = {
            "tools": [{"type": "function", "function": function}],
            "tool_choice": "required",
            "tools_pydantic": [CiteEvidence],
        }
        messages = [
            SystemMessage(
                content=(
                    "You are a world class algorithm to answer "
                    "questions with correct and exact citations."
                )
            ),
            HumanMessage(
                content=(
                    "Answer question using the following context. "
                    "Use the provided function CiteEvidence() to cite your sources."
                )
            ),
            HumanMessage(content=context),
            HumanMessage(content=f"Question: {question}"),
            HumanMessage(
                content=(
                    "Tips: Make sure to cite your sources, "
                    "and use exact copied start/end phrases from the context."
                )
            ),
        ]
        return messages, llm_kwargs

    def invoke(self, context: str, question: str):
        messages, llm_kwargs = self.prepare_llm(context, question)
        try:
            print("CitationPipeline: invoking LLM")
            llm_output = self.get_from_path("llm").invoke(messages, **llm_kwargs)
            print("CitationPipeline: finish invoking LLM")
            if not llm_output.additional_kwargs.get("tool_calls"):
                return None

            first_func = llm_output.additional_kwargs["tool_calls"][0]

            if "function" in first_func:
                # openai and cohere format
                function_output = first_func["function"]["arguments"]
            else:
                # anthropic format
                function_output = first_func["args"]

            print("CitationPipeline:", function_output)

            if isinstance(function_output, str):
                output = CiteEvidence.parse_raw(function_output)
            else:
                output = CiteEvidence.parse_obj(function_output)
        except Exception as e:
            print(e)
            return None

        return output

    async def ainvoke(self, context: str, question: str):
        raise NotImplementedError()
