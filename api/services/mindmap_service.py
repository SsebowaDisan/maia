from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from ktem.db.models import engine
from maia.mindmap.indexer import build_knowledge_map

from api.context import ApiContext


def _normalize_map_type(raw: str) -> str:
    value = " ".join(str(raw or "").split()).strip().lower()
    if value in {"evidence", "citation", "claims"}:
        return "evidence"
    return "structure"


def _source_hint(source_name: str) -> str:
    lower_name = str(source_name or "").lower()
    if lower_name.startswith("http://") or lower_name.startswith("https://"):
        return "web"
    if lower_name.endswith(".pdf"):
        return "pdf"
    return ""


def _load_source_documents(
    *,
    context: ApiContext,
    user_id: str,
    source_id: str,
    max_chunks: int = 120,
) -> tuple[str, list[dict[str, Any]]]:
    try:
        index = context.get_index(None)
        Source = index._resources["Source"]
        IndexTable = index._resources["Index"]
        doc_store = index._resources["DocStore"]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mind-map index resources unavailable: {exc}")

    with Session(engine) as session:
        source_stmt = select(Source).where(Source.id == source_id)
        if index.config.get("private", False):
            source_stmt = source_stmt.where(Source.user == user_id)
        source_row = session.exec(source_stmt).first()
        if source_row is None:
            raise HTTPException(status_code=404, detail="Source not found.")

        relation_rows = session.execute(
            select(IndexTable.target_id)
            .where(
                IndexTable.relation_type == "document",
                IndexTable.source_id == source_id,
            )
            .limit(max(24, int(max_chunks))),
        ).all()

    target_ids = [str(row[0]) for row in relation_rows if row and row[0]]
    if not target_ids:
        return str(source_row.name or "Indexed source"), []

    try:
        docs = doc_store.get(target_ids)
    except Exception:
        docs = []

    normalized_docs: list[dict[str, Any]] = []
    for idx, doc in enumerate(docs or []):
        metadata = dict(getattr(doc, "metadata", {}) or {})
        metadata.setdefault("source_id", str(source_id))
        metadata.setdefault("source_name", str(source_row.name or "Indexed source"))
        metadata.setdefault("file_name", str(source_row.name or "Indexed source"))
        normalized_docs.append(
            {
                "doc_id": str(getattr(doc, "doc_id", f"doc_{idx + 1}") or f"doc_{idx + 1}"),
                "text": str(getattr(doc, "text", "") or ""),
                "metadata": metadata,
            }
        )
    return str(source_row.name or "Indexed source"), normalized_docs


def build_source_mindmap(
    *,
    context: ApiContext,
    user_id: str,
    source_id: str,
    map_type: str = "structure",
    max_depth: int = 4,
    include_reasoning_map: bool = True,
) -> dict[str, Any]:
    source_name, documents = _load_source_documents(
        context=context,
        user_id=user_id,
        source_id=source_id,
    )
    if not documents:
        raise HTTPException(status_code=404, detail="No indexed chunks found for this source.")

    map_type_norm = _normalize_map_type(map_type)
    clipped_depth = max(2, min(8, int(max_depth)))
    map_title = f"Map for {source_name}"
    context_preview = "\n\n".join(str(row.get("text", "") or "") for row in documents[:8])
    return build_knowledge_map(
        question=map_title,
        context=context_preview,
        documents=documents,
        answer_text="",
        max_depth=clipped_depth,
        include_reasoning_map=bool(include_reasoning_map),
        source_type_hint=_source_hint(source_name),
        focus={"source_id": source_id, "source_name": source_name},
        map_type=map_type_norm,
    )


def to_markdown(payload: dict[str, Any]) -> str:
    map_title = str(payload.get("title", "Mind-map") or "Mind-map")
    lines: list[str] = [f"# {map_title}"]
    tree = payload.get("tree")
    if isinstance(tree, dict):
        lines.append("")

        def walk(node: dict[str, Any], depth: int) -> None:
            title = str(node.get("title", node.get("id", "Node")) or "Node")
            page = str(node.get("page", "") or "").strip()
            label = f"{title} (page {page})" if page else title
            lines.append(f"{'  ' * depth}- {label}")
            for child in node.get("children", []) if isinstance(node.get("children"), list) else []:
                if isinstance(child, dict):
                    walk(child, depth + 1)

        walk(tree, 0)
        return "\n".join(lines)

    lines.append("")
    lines.append("## Nodes")
    for node in payload.get("nodes", []) if isinstance(payload.get("nodes"), list) else []:
        if not isinstance(node, dict):
            continue
        lines.append(f"- {str(node.get('title', node.get('id', 'Node')))}")
    return "\n".join(lines)
