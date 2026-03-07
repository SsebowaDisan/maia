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


def _compact_text(raw: Any, *, max_len: int = 180) -> str:
    text = " ".join(str(raw or "").split()).strip()
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3].rstrip()}..."


def _work_graph_action_node_type(action: dict[str, Any]) -> str:
    action_class = str(action.get("action_class") or "").strip().lower()
    if action_class == "read":
        return "research"
    if action_class == "draft":
        return "email_draft"
    if action_class == "execute":
        return "api_operation"
    return "plan_step"


def _work_graph_action_status(raw_status: str) -> str:
    value = str(raw_status or "").strip().lower()
    if value == "success":
        return "completed"
    if value == "failed":
        return "failed"
    if value == "skipped":
        return "blocked"
    return "queued"


def _build_tree_view(payload: dict[str, Any]) -> dict[str, Any]:
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


def build_agent_work_graph(
    *,
    request_message: str,
    actions_taken: list[dict[str, Any]] | None,
    sources_used: list[dict[str, Any]] | None = None,
    map_type: str = "work_graph",
    max_depth: int = 4,
    run_id: str = "",
) -> dict[str, Any]:
    map_type_norm = _normalize_map_type(map_type)
    clipped_depth = max(2, min(8, int(max_depth)))
    max_steps = max(6, min(64, clipped_depth * 10))
    root_id = f"task_{str(run_id).strip()}" if str(run_id).strip() else "task_root"
    root_title = _compact_text(request_message or "Agent execution", max_len=120)
    nodes: list[dict[str, Any]] = [
        {
            "id": root_id,
            "title": root_title or "Agent execution",
            "text": "Execution plan and runtime outcomes",
            "node_type": "task",
            "status": "active",
            "confidence": 0.9,
        }
    ]
    edges: list[dict[str, Any]] = []

    action_rows = actions_taken if isinstance(actions_taken, list) else []
    source_rows = sources_used if isinstance(sources_used, list) else []
    last_node_id = root_id
    success_count = 0
    failed_count = 0

    for index, row in enumerate(action_rows[:max_steps], start=1):
        if not isinstance(row, dict):
            continue
        action_id = f"plan_step_{index}"
        raw_status = str(row.get("status", "") or "")
        status = _work_graph_action_status(raw_status)
        if status == "completed":
            success_count += 1
        if status == "failed":
            failed_count += 1
        tool_id = _compact_text(row.get("tool_id", ""), max_len=120)
        summary = _compact_text(row.get("summary", ""), max_len=160) or tool_id or f"Step {index}"
        action_class = _compact_text(row.get("action_class", ""), max_len=40) or "execute"
        confidence = 0.9 if status == "completed" else 0.35 if status == "failed" else 0.55
        nodes.append(
            {
                "id": action_id,
                "title": summary,
                "text": f"{action_class} via {tool_id or 'runtime tool'}",
                "node_type": _work_graph_action_node_type(row),
                "status": status,
                "confidence": confidence,
                "tool_id": tool_id,
                "action_class": action_class,
                "started_at": str(row.get("started_at", "") or ""),
                "ended_at": str(row.get("ended_at", "") or ""),
            }
        )
        edges.append(
            {
                "id": f"{last_node_id}->{action_id}",
                "source": last_node_id,
                "target": action_id,
                "type": "hierarchy",
                "edge_family": "sequential",
            }
        )
        last_node_id = action_id

    for source_index, row in enumerate(source_rows[:24], start=1):
        if not isinstance(row, dict):
            continue
        node_id = f"evidence_{source_index}"
        source_label = _compact_text(
            row.get("label") or row.get("url") or row.get("file_id") or f"Evidence {source_index}",
            max_len=120,
        )
        nodes.append(
            {
                "id": node_id,
                "title": source_label,
                "text": _compact_text(row.get("source_type"), max_len=80) or "source",
                "node_type": "artifact",
                "status": "completed",
                "source_type": str(row.get("source_type", "") or ""),
                "url": str(row.get("url", "") or ""),
                "file_id": str(row.get("file_id", "") or ""),
            }
        )
        edges.append(
            {
                "id": f"{last_node_id}->{node_id}",
                "source": last_node_id,
                "target": node_id,
                "type": "hierarchy",
                "edge_family": "evidence",
            }
        )
        last_node_id = node_id

    total_actions = max(1, success_count + failed_count)
    verification_status = "failed" if failed_count > 0 else "completed"
    verification_node_id = "verification_summary"
    nodes.append(
        {
            "id": verification_node_id,
            "title": "Verification summary",
            "text": f"{success_count} successful actions, {failed_count} failed actions",
            "node_type": "verification",
            "status": verification_status,
            "confidence": round(success_count / total_actions, 2),
        }
    )
    edges.append(
        {
            "id": f"{last_node_id}->{verification_node_id}",
            "source": last_node_id,
            "target": verification_node_id,
            "type": "hierarchy",
            "edge_family": "verification",
        }
    )

    base_payload: dict[str, Any] = {
        "version": 2,
        "map_type": "work_graph",
        "kind": "work_graph",
        "title": f"Work graph - {root_title or 'Agent execution'}",
        "root_id": root_id,
        "nodes": nodes,
        "edges": edges,
        "graph": {
            "schema": "work_graph.v1",
            "run_id": str(run_id or ""),
            "action_count": len(action_rows),
            "source_count": len(source_rows),
        },
        "settings": {
            "map_type": "work_graph",
            "graph_mode": "execution",
        },
    }
    base_payload["tree"] = _build_tree_view(base_payload)

    variants: dict[str, dict[str, Any]] = {}
    for variant_key, kind in (
        ("work_graph", "work_graph"),
        ("structure", "graph"),
        ("evidence", "graph"),
    ):
        variant_payload = {**base_payload, "map_type": variant_key, "kind": kind}
        variant_payload["tree"] = _build_tree_view(variant_payload)
        variants[variant_key] = variant_payload

    selected_payload = dict(variants.get(map_type_norm, variants["work_graph"]))
    selected_payload["variants"] = {
        key: value for key, value in variants.items() if key != selected_payload["map_type"]
    }
    selected_payload.setdefault("settings", {})
    selected_payload["settings"]["map_type"] = selected_payload["map_type"]
    return selected_payload


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
