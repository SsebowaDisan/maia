import logging
import json
from textwrap import dedent

from ktem.llms.manager import llms

from maia.base import BaseComponent, Document, Node
from maia.llms import ChatLLM
from maia.mindmap.indexer import build_knowledge_map, serialize_map_payload

logger = logging.getLogger(__name__)


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

    def run(self, question: str, context: str, **kwargs) -> Document:  # type: ignore
        documents = kwargs.get("documents") or kwargs.get("docs") or kwargs.get("retrieved_docs") or []
        answer_text = str(kwargs.get("answer_text", "") or "")
        source_type_hint = str(kwargs.get("source_type_hint", "") or "")
        focus = kwargs.get("focus")
        try:
            max_depth = int(kwargs.get("max_depth", self.default_max_depth))
        except Exception:
            max_depth = self.default_max_depth
        include_reasoning_map = bool(
            kwargs.get("include_reasoning_map", self.default_include_reasoning_map)
        )

        payload = build_knowledge_map(
            question=str(question or ""),
            context=str(context or ""),
            documents=documents,
            answer_text=answer_text,
            max_depth=max_depth,
            include_reasoning_map=include_reasoning_map,
            source_type_hint=source_type_hint,
            focus=focus if isinstance(focus, dict) else None,
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
