import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Generator

import numpy as np

from maia.base import AIMessage, Document, HumanMessage, SystemMessage
from maia.llms import PromptTemplate

from .citation_qa import (
    MAIA_CITATION_FUZZY_MATCH_ENABLED,
    MAX_IMAGES,
    AnswerWithContextPipeline,
    _compute_span_strength,
)
from .highlight_boxes import (
    extract_highlight_boxes_from_metadata,
    merge_adjacent_highlight_boxes,
)
from .format_context import EVIDENCE_MODE_FIGURE
from .utils import find_start_end_phrase, find_start_end_phrase_fuzzy

DEFAULT_QA_CITATION_PROMPT = """
Use the following pieces of context to answer the question at the end.
Provide DETAILED ansswer with clear explanation.
Format answer with easy to follow bullets / paragraphs.
If you don't know the answer, just say that you don't know, don't try to make up an answer.
Use the same language as the question to response.

CONTEXT:
----
{context}
----

Answer using this format:
CITATION LIST

// the index in this array
CITATION【number】

// output 2 phrase to mark start and end of the relevant span
// each has ~ 6 words
// MUST COPY EXACTLY from the CONTEXT
// NO CHANGE or REPHRASE
// RELEVANT_SPAN_FROM_CONTEXT
START_PHRASE: string
END_PHRASE: string

// When you answer, ensure to add citations from the documents
// in the CONTEXT with a number that corresponds to the answersInText array.
// (in the form [number])
// Try to include the number after each facts / statements you make.
// You can create as many citations as you need.
// Citation numbering rules:
// - Assign citation numbers sequentially starting from 1.
// - Reuse the same number when citing the same source span.
// - Do not reuse a number for a different source span.
FINAL ANSWER
string

STRICTLY FOLLOW THIS EXAMPLE:
CITATION LIST

CITATION【1】

START_PHRASE: Known as fixed-size chunking , the traditional
END_PHRASE: not degrade the final retrieval performance.

CITATION【2】

START_PHRASE: Fixed-size Chunker This is our baseline chunker
END_PHRASE: this shows good retrieval quality.

FINAL ANSWER
An alternative to semantic chunking is fixed-size chunking. This traditional method involves splitting documents into chunks of a predetermined or user-specified size, regardless of semantic content, which is computationally efficient【1】. However, it may result in the fragmentation of semantically related content, thereby potentially degrading retrieval performance【1】【2】.

QUESTION: {question}\n
ANSWER:
"""  # noqa

START_ANSWER = "FINAL ANSWER"
START_CITATION = "CITATION LIST"
CITATION_PATTERN = r"citation【(\d+)】"
START_ANSWER_PATTERN = "start_phrase:"
END_ANSWER_PATTERN = "end_phrase:"
INLINE_CITATION_RE = re.compile(r"【(\d+)】|\[(\d+)\]")
MERGED_INLINE_CITATION_RE = re.compile(
    r"【\s*(\d+\s*(?:,\s*\d+\s*)+)】|\[\s*(\d+\s*(?:,\s*\d+\s*)+)\]"
)


@dataclass
class InlineEvidence:
    """List of evidences to support the answer."""

    start_phrase: str | None = None
    end_phrase: str | None = None
    idx: int | None = None


class AnswerWithInlineCitation(AnswerWithContextPipeline):
    """Answer the question based on the evidence with inline citation"""

    qa_citation_template: str = DEFAULT_QA_CITATION_PROMPT

    def get_prompt(self, question, evidence, evidence_mode: int):
        """Prepare the prompt and other information for LLM"""
        prompt_template = PromptTemplate(self.qa_citation_template)

        prompt = prompt_template.populate(
            context=evidence,
            question=question,
            safe=False,
        )

        return prompt, evidence

    def answer_to_citations(self, answer) -> list[InlineEvidence]:
        citations: list[InlineEvidence] = []
        lines = answer.split("\n")

        current_evidence = None

        for line in lines:
            # check citation idx using regex
            match = re.match(CITATION_PATTERN, line.lower())

            if match:
                try:
                    parsed_citation_idx = int(match.group(1))
                except ValueError:
                    parsed_citation_idx = None

                # conclude the current evidence if exists
                if current_evidence:
                    citations.append(current_evidence)
                    current_evidence = None

                current_evidence = InlineEvidence(idx=parsed_citation_idx)
            else:
                for keyword in [START_ANSWER_PATTERN, END_ANSWER_PATTERN]:
                    if line.lower().startswith(keyword):
                        matched_phrase = line[len(keyword) :].strip()
                        if not current_evidence:
                            current_evidence = InlineEvidence(idx=None)

                        if keyword == START_ANSWER_PATTERN:
                            current_evidence.start_phrase = matched_phrase
                        else:
                            current_evidence.end_phrase = matched_phrase

                        break

            if (
                current_evidence
                and current_evidence.end_phrase
                and current_evidence.start_phrase
            ):
                citations.append(current_evidence)
                current_evidence = None

        if current_evidence:
            citations.append(current_evidence)

        return citations

    @staticmethod
    def _split_merged_citations(answer: str) -> str:
        def split_match(match: re.Match) -> str:
            payload = (match.group(1) or match.group(2) or "").strip()
            if not payload:
                return match.group(0)
            parts = []
            for raw in payload.split(","):
                cleaned = raw.strip()
                if not cleaned.isdigit():
                    return match.group(0)
                parts.append(str(int(cleaned)))
            if len(parts) <= 1:
                return match.group(0)
            return "".join(f"【{part}】" for part in parts)

        return MERGED_INLINE_CITATION_RE.sub(split_match, str(answer or ""))

    @staticmethod
    def _extract_citation_indices(answer: str) -> list[int]:
        indices: list[int] = []
        for match in INLINE_CITATION_RE.finditer(str(answer or "")):
            raw_value = match.group(1) or match.group(2)
            if not raw_value:
                continue
            try:
                indices.append(int(raw_value))
            except ValueError:
                continue
        return indices

    @staticmethod
    def _normalize_citation_mapping(
        answer: str, citations: list[InlineEvidence]
    ) -> tuple[str, dict[int, int]]:
        normalized_answer = AnswerWithInlineCitation._split_merged_citations(answer)
        seen: set[int] = set()
        ordered_indices: list[int] = []

        for idx in AnswerWithInlineCitation._extract_citation_indices(normalized_answer):
            if idx in seen:
                continue
            seen.add(idx)
            ordered_indices.append(idx)

        for evidence_pos, evidence in enumerate(citations):
            evidence_idx = evidence.idx if evidence.idx is not None else evidence_pos + 1
            if evidence_idx in seen:
                continue
            seen.add(evidence_idx)
            ordered_indices.append(evidence_idx)

        mapping = {old_idx: new_idx for new_idx, old_idx in enumerate(ordered_indices, start=1)}
        return normalized_answer, mapping

    @staticmethod
    def _apply_citation_mapping(answer: str, index_mapping: dict[int, int]) -> str:
        text = str(answer or "")
        if not index_mapping:
            return text

        def replace(match: re.Match) -> str:
            raw_value = match.group(1) or match.group(2)
            if not raw_value:
                return match.group(0)
            try:
                old_idx = int(raw_value)
            except ValueError:
                return match.group(0)
            new_idx = index_mapping.get(old_idx, old_idx)
            return f"【{new_idx}】"

        return INLINE_CITATION_RE.sub(replace, text)

    def replace_citation_with_link(self, answer: str):
        answer = self._split_merged_citations(answer)
        seen: set[int] = set()

        def replace(match: re.Match) -> str:
            raw_value = match.group(1) or match.group(2)
            if not raw_value:
                return ""
            try:
                citation_id = int(raw_value)
            except ValueError:
                return ""
            if citation_id in seen:
                return ""
            seen.add(citation_id)
            return (
                "<a href='#' class='citation' "
                f"id='mark-{citation_id}'>【{citation_id}】</a>"
            )

        answer = INLINE_CITATION_RE.sub(replace, answer)
        answer = answer.replace(START_CITATION, "")
        return answer

    def stream(  # type: ignore
        self,
        question: str,
        evidence: str,
        evidence_mode: int = 0,
        images: list[str] = [],
        **kwargs,
    ) -> Generator[Document, None, Document]:
        history = kwargs.get("history", [])
        print(f"Got {len(images)} images")
        # check if evidence exists, use QA prompt
        if evidence:
            prompt, evidence = self.get_prompt(question, evidence, evidence_mode)
        else:
            prompt = question

        output = ""
        logprobs = []

        citation = None
        mindmap = None

        messages = []
        if self.system_prompt:
            messages.append(SystemMessage(content=self.system_prompt))

        for human, ai in history[-self.n_last_interactions :]:
            messages.append(HumanMessage(content=human))
            messages.append(AIMessage(content=ai))

        if self.use_multimodal and evidence_mode == EVIDENCE_MODE_FIGURE:
            # create image message:
            messages.append(
                HumanMessage(
                    content=[
                        {"type": "text", "text": prompt},
                    ]
                    + [
                        {
                            "type": "image_url",
                            "image_url": {"url": image},
                        }
                        for image in images[:MAX_IMAGES]
                    ],
                )
            )
        else:
            # append main prompt
            messages.append(HumanMessage(content=prompt))

        final_answer = ""

        try:
            # try streaming first
            print("Trying LLM streaming")
            for out_msg in self.llm.stream(messages):
                if evidence:
                    if START_ANSWER in output:
                        if not final_answer:
                            try:
                                left_over_answer = output.split(START_ANSWER)[
                                    1
                                ].lstrip()
                            except IndexError:
                                left_over_answer = ""
                            if left_over_answer:
                                out_msg.text = left_over_answer + out_msg.text

                        final_answer += (
                            out_msg.text.lstrip() if not final_answer else out_msg.text
                        )
                        yield Document(channel="chat", content=out_msg.text)

                        # check for the edge case of citation list is repeated
                        # with smaller LLMs
                        if START_CITATION in out_msg.text:
                            break
                else:
                    yield Document(channel="chat", content=out_msg.text)

                output += out_msg.text
                logprobs += out_msg.logprobs
        except NotImplementedError:
            print("Streaming is not supported, falling back to normal processing")
            output = self.llm(messages).text
            yield Document(channel="chat", content=output)

        if logprobs:
            qa_score = np.exp(np.average(logprobs))
        else:
            qa_score = None

        citation = self.answer_to_citations(output)
        normalized_answer, citation_mapping = self._normalize_citation_mapping(
            final_answer, citation
        )
        if citation_mapping:
            for evidence_pos, evidence in enumerate(citation):
                evidence_idx = evidence.idx if evidence.idx is not None else evidence_pos + 1
                evidence.idx = citation_mapping.get(evidence_idx, evidence_idx)
            normalized_answer = self._apply_citation_mapping(
                normalized_answer, citation_mapping
            )

        if self.enable_mindmap:
            try:
                mindmap = self.create_mindmap_pipeline(
                    context=evidence,
                    question=question,
                    docs=kwargs.get("retrieved_docs", []),
                    answer_text=final_answer,
                    max_depth=kwargs.get("mindmap_max_depth", 4),
                    include_reasoning_map=kwargs.get("include_reasoning_map", True),
                    source_type_hint=kwargs.get("mindmap_source_type_hint", ""),
                    focus=kwargs.get("mindmap_focus", {}),
                    map_type=kwargs.get("mindmap_map_type", "structure"),
                )
            except Exception as exc:
                print("Mindmap generation failed:", exc)
                mindmap = None

        # convert citation to link
        answer = Document(
            text=normalized_answer,
            metadata={
                "citation_viz": self.enable_citation_viz,
                "mindmap": mindmap,
                "citation": citation,
                "citation_index_mapping": citation_mapping,
                "qa_score": qa_score,
            },
        )

        # yield the final answer
        final_answer = self.replace_citation_with_link(normalized_answer)

        if final_answer:
            yield Document(channel="chat", content=None)
            yield Document(channel="chat", content=final_answer)

        return answer

    def match_evidence_with_context(self, answer, docs) -> dict[str, list[dict]]:
        """Match the evidence with the context"""
        spans: dict[str, list[dict]] = defaultdict(list)

        if not answer.metadata["citation"]:
            return spans

        evidences = answer.metadata["citation"]

        for e_id, evidence in enumerate(evidences):
            start_phrase, end_phrase = evidence.start_phrase, evidence.end_phrase
            evidence_idx = evidence.idx

            if evidence_idx is None:
                evidence_idx = e_id + 1

            best_match = None
            best_match_length = 0
            best_match_doc_idx = None
            best_match_quality = "fuzzy"

            for doc in docs:
                match, match_length = find_start_end_phrase(
                    start_phrase, end_phrase, doc.text
                )
                local_quality = "exact"
                if match is None and MAIA_CITATION_FUZZY_MATCH_ENABLED:
                    match, match_length = find_start_end_phrase_fuzzy(
                        start_phrase=start_phrase,
                        end_phrase=end_phrase,
                        context=doc.text,
                    )
                    if match is not None:
                        local_quality = "fuzzy"
                if best_match is None or (
                    match is not None and match_length > best_match_length
                ):
                    best_match = match
                    best_match_length = match_length
                    best_match_doc_idx = doc.doc_id
                    best_match_quality = local_quality

            if best_match is not None and best_match_doc_idx is not None:
                matched_doc = next(
                    (doc for doc in docs if str(doc.doc_id) == str(best_match_doc_idx)),
                    None,
                )
                span_text = ""
                span_strength = 0.0
                if matched_doc is not None:
                    span_text = str(
                        matched_doc.text[best_match[0] : best_match[1]] if matched_doc.text else ""
                    )
                    span_strength = _compute_span_strength(
                        doc=matched_doc,
                        span_text=span_text,
                        is_exact_match=(best_match_quality == "exact"),
                    )
                highlight_boxes = (
                    merge_adjacent_highlight_boxes(
                        extract_highlight_boxes_from_metadata((matched_doc.metadata or {}) if matched_doc else {})
                    )
                    if matched_doc is not None
                    else []
                )
                spans[best_match_doc_idx].append(
                    {
                        "start": best_match[0],
                        "end": best_match[1],
                        "char_start": best_match[0],
                        "char_end": best_match[1],
                        "unit_id": str((matched_doc.metadata or {}).get("unit_id", "") or "")
                        if matched_doc is not None
                        else "",
                        "highlight_boxes": highlight_boxes,
                        "match_quality": best_match_quality,
                        "idx": evidence_idx,
                        "is_exact_match": bool(best_match_quality == "exact"),
                        "strength_score": span_strength,
                    }
                )
        return spans
