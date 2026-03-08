from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from ktem.db.models import engine


if False:  # typing-only guard
    from api.context import ApiContext


def normalize_map_type(raw: str) -> str:
    value = " ".join(str(raw or "").split()).strip().lower()
    if value in {"context", "context_mindmap", "context-mindmap", "context mindmap"}:
        return "context_mindmap"
    if value in {"evidence", "citation", "claims"}:
        return "evidence"
    if value in {
        "work_graph",
        "work-graph",
        "work graph",
        "execution",
        "execution_graph",
        "execution graph",
    }:
        return "work_graph"
    return "structure"


def source_hint(source_name: str) -> str:
    lower_name = str(source_name or "").lower()
    if lower_name.startswith("http://") or lower_name.startswith("https://"):
        return "web"
    if lower_name.endswith(".pdf"):
        return "pdf"
    return ""


def load_source_documents(
    *,
    context: Any,
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


def compact_text(raw: Any, *, max_len: int = 180) -> str:
    text = " ".join(str(raw or "").split()).strip()
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3].rstrip()}..."


def work_graph_action_node_type(action: dict[str, Any]) -> str:
    action_class = str(action.get("action_class") or "").strip().lower()
    if action_class == "read":
        return "research"
    if action_class == "draft":
        return "email_draft"
    if action_class == "execute":
        return "api_operation"
    return "plan_step"


def work_graph_action_status(raw_status: str) -> str:
    value = str(raw_status or "").strip().lower()
    if value == "success":
        return "completed"
    if value == "failed":
        return "failed"
    if value == "skipped":
        return "blocked"
    return "queued"


def build_tree_view(payload: dict[str, Any]) -> dict[str, Any]:
    root_id = str(payload.get("root_id", "") or "")
    node_rows = payload.get("nodes", [])
    edge_rows = payload.get("edges", [])
    if not root_id or not isinstance(node_rows, list) or not isinstance(edge_rows, list):
        return {}
    node_by_id = {
        str(node.get("id", "")): node
        for node in node_rows
        if isinstance(node, dict) and str(node.get("id", "")).strip()
    }
    children_by_parent: dict[str, list[str]] = {}
    for edge in edge_rows:
        if not isinstance(edge, dict):
            continue
        edge_type = str(edge.get("type", "") or "")
        if edge_type not in {"", "hierarchy"}:
            continue
        source_id = str(edge.get("source", "") or "")
        target_id = str(edge.get("target", "") or "")
        if not source_id or not target_id:
            continue
        children_by_parent.setdefault(source_id, []).append(target_id)

    visited: set[str] = set()

    def walk(node_id: str) -> dict[str, Any]:
        node = node_by_id.get(node_id, {})
        if node_id in visited:
            return {
                "id": node_id,
                "title": str(node.get("title", node_id) or node_id),
                "type": str(node.get("node_type") or node.get("type") or "plan_step"),
                "children": [],
            }
        visited.add(node_id)
        return {
            "id": node_id,
            "title": str(node.get("title", node_id) or node_id),
            "text": str(node.get("text", "") or ""),
            "type": str(node.get("node_type") or node.get("type") or "plan_step"),
            "children": [walk(child_id) for child_id in children_by_parent.get(node_id, [])],
        }

    return walk(root_id)


def classify_source_type(row: dict[str, Any]) -> str:
    source_type = str(row.get("source_type", "") or "").lower()
    url = str(row.get("url", "") or "")
    file_id = str(row.get("file_id", "") or "")
    if source_type in {"web", "web_source", "browser", "news", "newsapi", "arxiv", "reddit", "sec_edgar"}:
        return "web"
    if url and (url.startswith("http://") or url.startswith("https://")):
        return "web"
    if file_id or source_type in {"pdf", "document", "doc", "file"}:
        return "doc"
    return "other"


def phase_label(node_type: str) -> str:
    return {
        "plan_step": "Planning",
        "research": "Research",
        "email_draft": "Content Creation",
        "api_operation": "Operations",
    }.get(node_type, node_type.replace("_", " ").title())


def phase_status(statuses: list[str]) -> str:
    if all(s == "completed" for s in statuses):
        return "completed"
    if any(s == "failed" for s in statuses):
        return "failed"
    if any(s == "running" for s in statuses):
        return "running"
    return "queued"
