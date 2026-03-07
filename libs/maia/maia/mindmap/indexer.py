from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .evidence_map import build_evidence_map
from .extractors import (
    MAX_DEFAULT_NODES,
    crawl_website_to_graph,
    jaccard,
    parse_pdf_to_tree,
    stable_id,
    tokenize,
    truncate,
)
from .structure_map import build_structure_map


def _build_reasoning_context_nodes(
    nodes: list[dict[str, Any]],
    question: str,
    answer_text: str,
    limit: int = 4,
) -> list[dict[str, Any]]:
    query_tokens = tokenize(question) | tokenize(answer_text)
    scored: list[tuple[float, dict[str, Any]]] = []
    for node in nodes:
        if node.get("node_type") in {"root", "source", "page"} and node.get("children"):
            continue
        node_tokens = tokenize(node.get("title", "")) | tokenize(node.get("text", ""))
        score = jaccard(query_tokens, node_tokens)
        if score <= 0.0:
            continue
        scored.append((score, node))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [row[1] for row in scored[: max(1, limit)]]


def build_reasoning_map(
    *,
    question: str,
    answer_text: str,
    context_nodes: list[dict[str, Any]],
    reasoning_steps: list[str] | None = None,
) -> dict[str, Any]:
    steps = reasoning_steps or [
        "Select relevant context nodes",
        "Synthesize evidence across selected nodes",
        "Draft grounded answer from cited context",
    ]
    q_node_id = "reasoning_q"
    a_node_id = "reasoning_a"
    nodes: list[dict[str, Any]] = [
        {"id": q_node_id, "label": truncate(question or "Question", 180), "kind": "question"},
    ]
    edges: list[dict[str, Any]] = []
    previous = q_node_id
    for idx, step in enumerate(steps, start=1):
        step_id = f"reasoning_step_{idx}"
        nodes.append({"id": step_id, "label": truncate(step, 180), "kind": "step"})
        edges.append({"id": f"reasoning_edge_{idx}", "source": previous, "target": step_id})
        previous = step_id
    for idx, node in enumerate(context_nodes, start=1):
        c_id = f"context_{idx}"
        nodes.append(
            {
                "id": c_id,
                "label": truncate(node.get("title", "Context node"), 180),
                "kind": "context",
                "node_id": node.get("id", ""),
            }
        )
        edges.append({"id": f"context_edge_{idx}", "source": q_node_id, "target": c_id})
        edges.append({"id": f"context_to_step_{idx}", "source": c_id, "target": "reasoning_step_1"})
    nodes.append({"id": a_node_id, "label": truncate(answer_text or "Answer", 220), "kind": "answer"})
    edges.append({"id": "reasoning_edge_answer", "source": previous, "target": a_node_id})
    return {"layout": "horizontal", "nodes": nodes, "edges": edges}


def _build_tree_view(payload: dict[str, Any]) -> dict[str, Any]:
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    root_id = str(payload.get("root_id", "") or "")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not root_id:
        return {}

    node_by_id = {str(node.get("id", "")): node for node in nodes if isinstance(node, dict)}
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    cross_links_by_node: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if not source or not target:
            continue
        edge_type = str(edge.get("type", "") or "")
        if edge_type == "hierarchy":
            children_by_parent[source].append(target)
        else:
            cross_links_by_node[source].append(target)

    visited: set[str] = set()

    def build_node(node_id: str) -> dict[str, Any]:
        node = node_by_id.get(node_id, {})
        if node_id in visited:
            return {
                "id": node_id,
                "title": str(node.get("title", node_id)),
                "type": str(node.get("type") or node.get("node_type") or "structure"),
                "children": [],
                "crossLinks": [],
            }
        visited.add(node_id)
        children = [build_node(child_id) for child_id in children_by_parent.get(node_id, [])]
        return {
            "id": node_id,
            "title": str(node.get("title", node_id)),
            "text": str(node.get("text", "")),
            "page": str(node.get("page") or node.get("page_ref") or ""),
            "type": str(node.get("type") or node.get("node_type") or "structure"),
            "children": children,
            "crossLinks": cross_links_by_node.get(node_id, []),
        }

    return build_node(root_id)


def compute_balanced_tree_layout(
    *,
    root_id: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    max_depth: int = 4,
    depth_gap: int = 240,
    leaf_gap: int = 120,
) -> dict[str, dict[str, float]]:
    node_ids = {str(node.get("id", "")) for node in nodes if isinstance(node, dict)}
    if root_id not in node_ids:
        return {}

    children_by_parent: dict[str, list[str]] = defaultdict(list)
    depth_map: dict[str, int] = {root_id: 0}
    for edge in edges:
        if str(edge.get("type", "")) not in {"", "hierarchy"}:
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if not source or not target or source not in node_ids or target not in node_ids:
            continue
        children_by_parent[source].append(target)
    queue = [root_id]
    while queue:
        current = queue.pop(0)
        for child in children_by_parent.get(current, []):
            if child in depth_map:
                continue
            depth_map[child] = depth_map[current] + 1
            queue.append(child)

    side_by_node: dict[str, str] = {root_id: "center"}
    top_children = children_by_parent.get(root_id, [])
    for idx, child in enumerate(top_children):
        side_by_node[child] = "left" if idx % 2 == 0 else "right"
    walk_queue = list(top_children)
    while walk_queue:
        current = walk_queue.pop(0)
        current_side = side_by_node.get(current, "right")
        for child in children_by_parent.get(current, []):
            side_by_node[child] = current_side
            walk_queue.append(child)

    def count_leaves(node_id: str) -> int:
        if depth_map.get(node_id, max_depth + 1) >= max_depth:
            return 1
        children = [child for child in children_by_parent.get(node_id, []) if depth_map.get(child, max_depth + 1) <= max_depth]
        if not children:
            return 1
        return sum(count_leaves(child) for child in children)

    left_leaf_count = sum(count_leaves(child) for child in top_children if side_by_node.get(child) == "left")
    right_leaf_count = sum(count_leaves(child) for child in top_children if side_by_node.get(child) == "right")
    leaf_cursor = {
        "left": -((max(0, left_leaf_count - 1) * leaf_gap) / 2.0),
        "right": -((max(0, right_leaf_count - 1) * leaf_gap) / 2.0),
    }
    positions: dict[str, dict[str, float]] = {root_id: {"x": 0.0, "y": 0.0}}

    def place(node_id: str) -> float:
        side = side_by_node.get(node_id, "right")
        depth = depth_map.get(node_id, 1)
        x = float((-1 if side == "left" else 1) * depth * depth_gap)
        children = [child for child in children_by_parent.get(node_id, []) if depth_map.get(child, max_depth + 1) <= max_depth]
        if not children or depth >= max_depth:
            y = float(leaf_cursor[side])
            leaf_cursor[side] += float(leaf_gap)
            positions[node_id] = {"x": x, "y": y}
            return y
        child_y = [place(child) for child in children]
        y = float(sum(child_y) / max(1, len(child_y)))
        positions[node_id] = {"x": x, "y": y}
        return y

    for child in top_children:
        if depth_map.get(child, max_depth + 1) > max_depth:
            continue
        place(child)
    return positions


def parse_pdf_structure(
    pdf_file: str,
    *,
    max_depth: int = 4,
    node_limit: int = MAX_DEFAULT_NODES,
) -> dict[str, Any]:
    payload = parse_pdf_to_tree(pdf_file, max_depth=max_depth, node_limit=node_limit)
    payload["map_type"] = "structure"
    payload["tree"] = _build_tree_view(payload)
    return payload


def crawl_web(
    urls: list[str] | str,
    *,
    max_pages: int = 8,
    same_domain_only: bool = True,
    timeout_seconds: int = 8,
) -> dict[str, Any]:
    targets = [urls] if isinstance(urls, str) else [str(item) for item in (urls or []) if str(item).strip()]
    merged_nodes: list[dict[str, Any]] = []
    merged_edges: list[dict[str, Any]] = []
    root_id = ""
    seen_nodes: set[str] = set()
    seen_edges: set[str] = set()

    for idx, url in enumerate(targets):
        graph = crawl_website_to_graph(
            url,
            max_pages=max_pages,
            same_domain_only=same_domain_only,
            timeout_seconds=timeout_seconds,
        )
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        if idx == 0:
            root_id = str(graph.get("root_id", "") or "")
        for node in nodes if isinstance(nodes, list) else []:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", ""))
            if not node_id or node_id in seen_nodes:
                continue
            seen_nodes.add(node_id)
            node["type"] = "structure"
            merged_nodes.append(node)
        for edge in edges if isinstance(edges, list) else []:
            if not isinstance(edge, dict):
                continue
            edge_id = str(edge.get("id", "") or f"{edge.get('source')}->{edge.get('target')}")
            if edge_id in seen_edges:
                continue
            seen_edges.add(edge_id)
            merged_edges.append(edge)

    payload = {
        "version": 2,
        "map_type": "structure",
        "kind": "graph",
        "title": "Website structure map",
        "root_id": root_id or (merged_nodes[0]["id"] if merged_nodes else ""),
        "nodes": merged_nodes,
        "edges": merged_edges,
    }
    payload["tree"] = _build_tree_view(payload)
    return payload


def _sanitize_map_type(map_type: str) -> str:
    value = " ".join(str(map_type or "").split()).strip().lower()
    if value in {"evidence", "citation", "claims"}:
        return "evidence"
    if value in {
        "work_graph",
        "work-graph",
        "work graph",
        "execution_graph",
        "execution graph",
        "execution",
        "workflow",
    }:
        return "work_graph"
    return "structure"


def _work_graph_node_type(raw_type: str) -> str:
    value = str(raw_type or "").strip().lower()
    if value in {"root", "question", "topic"}:
        return "task"
    if value in {"source", "web_source", "page", "section", "chunk"}:
        return "research"
    if value in {"claim", "finding"}:
        return "verification"
    return "plan_step"


def _work_graph_edge_family(raw_type: str) -> str:
    value = str(raw_type or "").strip().lower()
    if value in {"hierarchy", "sequence", "next"}:
        return "sequential"
    if value in {"support", "citation", "evidence"}:
        return "evidence"
    if value in {"verify", "verification", "validated"}:
        return "verification"
    return "dependency"


def _build_work_graph_payload(
    *,
    structure_payload: dict[str, Any],
    evidence_payload: dict[str, Any],
) -> dict[str, Any]:
    structure_nodes = structure_payload.get("nodes", [])
    structure_edges = structure_payload.get("edges", [])
    mapped_nodes: list[dict[str, Any]] = []
    for node in structure_nodes if isinstance(structure_nodes, list) else []:
        if not isinstance(node, dict):
            continue
        mapped = dict(node)
        mapped["work_graph_type"] = _work_graph_node_type(
            str(node.get("node_type") or node.get("type") or "")
        )
        mapped.setdefault("status", "completed")
        mapped_nodes.append(mapped)

    mapped_edges: list[dict[str, Any]] = []
    for edge in structure_edges if isinstance(structure_edges, list) else []:
        if not isinstance(edge, dict):
            continue
        mapped = dict(edge)
        mapped["edge_family"] = _work_graph_edge_family(str(edge.get("type") or ""))
        mapped_edges.append(mapped)

    settings = dict(structure_payload.get("settings", {}) or {})
    settings["map_type"] = "work_graph"
    settings["graph_mode"] = "execution"
    payload: dict[str, Any] = {
        **structure_payload,
        "map_type": "work_graph",
        "kind": "work_graph",
        "nodes": mapped_nodes,
        "edges": mapped_edges,
        "settings": settings,
        "graph": {
            "schema": "work_graph.v1",
            "node_count": len(mapped_nodes),
            "edge_count": len(mapped_edges),
        },
    }
    payload["variants"] = {
        "structure": {**structure_payload, "map_type": "structure"},
        "evidence": {**evidence_payload, "map_type": "evidence"},
    }
    return payload


def build_knowledge_map(
    *,
    question: str,
    context: str,
    documents: list[Any] | None = None,
    answer_text: str = "",
    max_depth: int = 4,
    include_reasoning_map: bool = True,
    source_type_hint: str = "",
    focus: dict[str, Any] | None = None,
    node_limit: int = MAX_DEFAULT_NODES,
    map_type: str = "structure",
) -> dict[str, Any]:
    selected_map_type = _sanitize_map_type(map_type)
    focus_payload = focus if isinstance(focus, dict) else {}
    structure_payload = build_structure_map(
        question=question,
        context=context,
        documents=documents,
        max_depth=max_depth,
        source_type_hint=source_type_hint,
        focus=focus_payload,
        node_limit=node_limit,
    )
    evidence_payload = build_evidence_map(
        question=question,
        context=context,
        documents=documents,
        answer_text=answer_text,
        max_depth=max_depth,
        focus=focus_payload,
        node_limit=node_limit,
    )

    if selected_map_type == "evidence":
        payload = evidence_payload
    elif selected_map_type == "work_graph":
        payload = _build_work_graph_payload(
            structure_payload=structure_payload,
            evidence_payload=evidence_payload,
        )
    else:
        payload = structure_payload

    payload["map_type"] = selected_map_type
    payload.setdefault("settings", {})
    payload["settings"]["map_type"] = selected_map_type
    payload["tree"] = _build_tree_view(payload)
    if selected_map_type == "work_graph":
        variants = payload.get("variants", {})
        if isinstance(variants, dict):
            for variant_key in ("structure", "evidence"):
                variant_payload = variants.get(variant_key)
                if isinstance(variant_payload, dict):
                    variant_payload["tree"] = _build_tree_view(variant_payload)
    else:
        alternate = evidence_payload if selected_map_type == "structure" else structure_payload
        alt_key = "evidence" if selected_map_type == "structure" else "structure"
        payload["variants"] = {
            alt_key: {
                **alternate,
                "tree": _build_tree_view(alternate),
            },
        }

    if include_reasoning_map:
        context_nodes = _build_reasoning_context_nodes(
            list(payload.get("nodes", [])),
            question=question,
            answer_text=answer_text,
        )
        payload["reasoning_map"] = build_reasoning_map(
            question=question,
            answer_text=answer_text,
            context_nodes=context_nodes,
        )
    return payload


def serialize_map_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
