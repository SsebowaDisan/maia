import logging
import json
import re
from textwrap import dedent

from ktem.llms.manager import llms

from maia.base import BaseComponent, Document, HumanMessage, Node, SystemMessage
from maia.llms import ChatLLM
from maia.mindmap.indexer import build_knowledge_map, serialize_map_payload

logger = logging.getLogger(__name__)
TITLE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_/-]*")


MINDMAP_HTML_EXPORT_TEMPLATE = dedent(
    """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Mindmap</title>
    <style>
      svg.markmap {
        width: 100%;
        height: 100vh;
      }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/markmap-autoloader@0.16"></script>
  </head>
  <body>
    {markmap_div}
  </body>
</html>
"""
)


class CreateMindmapPipeline(BaseComponent):
    """Create a structured mind-map/knowledge-map JSON payload."""

    llm: ChatLLM = Node(default_callback=lambda _: llms.get_default())
    default_max_depth: int = 4
    default_include_reasoning_map: bool = True
    default_use_llm_titles: bool = True
    llm_title_batch_size: int = 24
    llm_title_node_cap: int = 120

    @staticmethod
    def _safe_payload_fragment(value: str, limit: int = 480) -> str:
        text = " ".join(str(value or "").split()).strip()
        return text[:limit]

    @staticmethod
    def _normalize_title(raw: str, *, min_words: int = 2, max_words: int = 6) -> str:
        text = " ".join(str(raw or "").split()).strip()
        if not text:
            return ""
        cleaned = re.sub(r"[`\"'{}\\[\\]<>|]+", " ", text)
        tokens = TITLE_TOKEN_RE.findall(cleaned)
        if len(tokens) < min_words:
            return ""
        if len(tokens) > max_words:
            tokens = tokens[:max_words]
        return " ".join(tokens)

    @classmethod
    def _fallback_title(
        cls,
        *,
        node: dict,
        question_tokens: list[str],
        min_words: int = 2,
        max_words: int = 6,
    ) -> str:
        source_tokens: list[str] = []
        for field in ("title", "text", "page_ref", "page", "id"):
            source_tokens.extend(TITLE_TOKEN_RE.findall(str(node.get(field, ""))))
        source_tokens.extend(question_tokens[:6])
        if not source_tokens:
            return ""
        words: list[str] = []
        seen: set[str] = set()
        for token in source_tokens:
            normalized = token.strip("_-/")
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            words.append(normalized)
            if len(words) >= max_words:
                break
        if len(words) < min_words:
            return ""
        return " ".join(words[:max_words])

    @staticmethod
    def _extract_json_array(raw: str) -> list[dict]:
        text = str(raw or "").strip()
        if not text:
            return []
        candidate = text
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []
        return [row for row in parsed if isinstance(row, dict)]

    @staticmethod
    def _collect_title_nodes(payload: dict, cap: int) -> list[dict]:
        nodes = payload.get("nodes")
        if not isinstance(nodes, list):
            return []
        result: list[dict] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", "")).strip()
            if not node_id:
                continue
            node_type = str(node.get("node_type", node.get("type", ""))).lower()
            if node_type in {"root", "source", "web_source"}:
                continue
            result.append(node)
            if len(result) >= max(1, int(cap)):
                break
        return result

    def _retitle_payload_with_llm(
        self,
        *,
        payload: dict,
        question: str,
        answer_text: str,
        min_words: int = 2,
        max_words: int = 6,
    ) -> None:
        nodes = self._collect_title_nodes(payload, cap=self.llm_title_node_cap)
        if not nodes:
            return

        question_tokens = TITLE_TOKEN_RE.findall(question or "")
        updates: dict[str, str] = {}
        batch_size = max(6, min(48, int(self.llm_title_batch_size)))

        for offset in range(0, len(nodes), batch_size):
            batch = nodes[offset : offset + batch_size]
            items = []
            for node in batch:
                items.append(
                    {
                        "id": str(node.get("id", "")),
                        "title": self._safe_payload_fragment(str(node.get("title", "")), limit=120),
                        "snippet": self._safe_payload_fragment(str(node.get("text", "")), limit=260),
                    }
                )

            messages = [
                SystemMessage(
                    content=(
                        "You rename mind-map nodes. Return ONLY a JSON array. "
                        "Each item must be {\"id\": string, \"title\": string}. "
                        "Each title must contain 2 to 6 words."
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {
                            "question": self._safe_payload_fragment(question, limit=220),
                            "answer": self._safe_payload_fragment(answer_text, limit=560),
                            "items": items,
                            "constraints": {
                                "word_count_min": min_words,
                                "word_count_max": max_words,
                            },
                        },
                        ensure_ascii=False,
                    )
                ),
            ]

            try:
                llm_output = self.get_from_path("llm").invoke(messages)
                rows = self._extract_json_array(getattr(llm_output, "content", ""))
            except Exception as exc:
                logger.warning("mindmap_llm_title_batch_failed error=%s", exc)
                rows = []

            for row in rows:
                node_id = str(row.get("id", "")).strip()
                if not node_id:
                    continue
                normalized = self._normalize_title(
                    str(row.get("title", "")),
                    min_words=min_words,
                    max_words=max_words,
                )
                if normalized:
                    updates[node_id] = normalized

        for node in nodes:
            node_id = str(node.get("id", "")).strip()
            replacement = updates.get(node_id, "")
            if not replacement:
                replacement = self._normalize_title(
                    str(node.get("title", "")),
                    min_words=min_words,
                    max_words=max_words,
                )
            if not replacement:
                replacement = self._fallback_title(
                    node=node,
                    question_tokens=question_tokens,
                    min_words=min_words,
                    max_words=max_words,
                )
            if replacement:
                node["title"] = replacement

    def _retitle_payloads_with_llm(
        self,
        *,
        payload: dict,
        question: str,
        answer_text: str,
    ) -> None:
        self._retitle_payload_with_llm(
            payload=payload,
            question=question,
            answer_text=answer_text,
        )
        variants = payload.get("variants")
        if not isinstance(variants, dict):
            return
        for variant in variants.values():
            if not isinstance(variant, dict):
                continue
            self._retitle_payload_with_llm(
                payload=variant,
                question=question,
                answer_text=answer_text,
            )

    def run(self, question: str, context: str, **kwargs) -> Document:  # type: ignore
        documents = kwargs.get("documents") or kwargs.get("docs") or kwargs.get("retrieved_docs") or []
        answer_text = str(kwargs.get("answer_text", "") or "")
        source_type_hint = str(kwargs.get("source_type_hint", "") or "")
        map_type = str(kwargs.get("map_type", "structure") or "structure")
        focus = kwargs.get("focus")
        try:
            max_depth = int(kwargs.get("max_depth", self.default_max_depth))
        except Exception:
            max_depth = self.default_max_depth
        include_reasoning_map = bool(
            kwargs.get("include_reasoning_map", self.default_include_reasoning_map)
        )
        use_llm_titles = bool(kwargs.get("use_llm_titles", self.default_use_llm_titles))

        payload = build_knowledge_map(
            question=str(question or ""),
            context=str(context or ""),
            documents=documents,
            answer_text=answer_text,
            max_depth=max_depth,
            include_reasoning_map=include_reasoning_map,
            source_type_hint=source_type_hint,
            focus=focus if isinstance(focus, dict) else None,
            map_type=map_type,
        )

        if use_llm_titles:
            self._retitle_payloads_with_llm(
                payload=payload,
                question=str(question or ""),
                answer_text=answer_text,
            )

        return Document(
            text=serialize_map_payload(payload),
            metadata={"mindmap": payload},
        )

    @staticmethod
    def parse_payload(value: object) -> dict:
        if isinstance(value, dict):
            return value
        if isinstance(value, Document):
            payload = value.metadata.get("mindmap")
            if isinstance(payload, dict):
                return payload
            try:
                return json.loads(str(value.text or ""))
            except Exception:
                return {}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}
