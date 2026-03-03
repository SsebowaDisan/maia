from __future__ import annotations

import json
from typing import Any

from .extractors import (
    MAX_DEFAULT_NODES,
    clean_text,
    coerce_page_label,
    crawl_website_to_graph,
    extract_multimodal_nodes,
    extract_page_outline,
    first_sentences,
    group_records_by_source,
    jaccard,
    normalize_records,
    parse_pdf_to_tree,
    sort_page_key,
    stable_id,
    tokenize,
    truncate,
    utc_now_iso,
)


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
    nodes.append(
        {"id": a_node_id, "label": truncate(answer_text or "Answer", 220), "kind": "answer"}
    )
    edges.append({"id": "reasoning_edge_answer", "source": previous, "target": a_node_id})
    return {"layout": "horizontal", "nodes": nodes, "edges": edges}


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
) -> dict[str, Any]:
    max_depth = max(1, min(8, int(max_depth)))
    node_limit = max(32, min(800, int(node_limit)))
    records = normalize_records(documents)
    focus_payload = dict(focus or {})
    map_title = truncate(question or "Knowledge map", 120) or "Knowledge map"

    root_id = stable_id(map_title, prefix="root")
    root_node = {
        "id": root_id,
        "title": map_title,
        "text": truncate(context, 260),
        "node_type": "root",
        "children": [],
        "related": [],
        "focus": bool(focus_payload),
    }
    nodes: list[dict[str, Any]] = [root_node]
    edges: list[dict[str, Any]] = []

    source_groups = group_records_by_source(records)
    if not source_groups and context.strip():
        source_groups = {
            "context": [
                {
                    "doc_id": "context",
                    "source_id": "context",
                    "source_name": "Context",
                    "page_label": "",
                    "text": context,
                    "unit_id": "",
                    "url": "",
                    "media_type": "text",
                    "image_origin": None,
                    "links": [],
                    "metadata": {},
                }
            ]
        }

    website_source_count = 0
    pdf_source_count = 0

    for source_id, rows in source_groups.items():
        source_name = rows[0].get("source_name", "Indexed source")
        source_url = clean_text(rows[0].get("url", ""))
        is_web = bool(source_url or str(source_name).startswith(("http://", "https://")))
        is_pdf = str(source_name).lower().endswith(".pdf")
        website_source_count += 1 if is_web else 0
        pdf_source_count += 1 if is_pdf else 0

        source_node_id = stable_id(f"{source_id}|{source_name}", prefix="src")
        source_node = {
            "id": source_node_id,
            "title": truncate(source_name, 120),
            "text": truncate(" ".join(row["text"] for row in rows[:3]), 240),
            "source_id": source_id,
            "source_name": source_name,
            "node_type": "web_source" if is_web else "source",
            "children": [],
            "related": [],
        }
        nodes.append(source_node)
        root_node["children"].append(source_node_id)
        edges.append(
            {
                "id": stable_id(f"{root_id}->{source_node_id}", prefix="edge"),
                "source": root_id,
                "target": source_node_id,
                "type": "hierarchy",
            }
        )

        page_groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            page_groups.setdefault(row.get("page_label", ""), []).append(row)
        sorted_pages = sorted(page_groups.keys(), key=sort_page_key) or [""]
        if not sorted_pages:
            sorted_pages = [""]
        for page_label in sorted_pages:
            page_rows = page_groups.get(page_label, rows)
            page_node_id = stable_id(
                f"{source_node_id}|page|{page_label or 'na'}",
                prefix="page",
            )
            page_title = f"Page {page_label}" if page_label else "Section"
            page_text = " ".join(row.get("text", "") for row in page_rows[:4])
            page_node = {
                "id": page_node_id,
                "title": truncate(page_title, 80),
                "text": truncate(page_text, 240),
                "source_id": source_id,
                "source_name": source_name,
                "page_ref": page_label or None,
                "node_type": "page",
                "children": [],
                "related": [],
            }
            nodes.append(page_node)
            source_node["children"].append(page_node_id)
            edges.append(
                {
                    "id": stable_id(f"{source_node_id}->{page_node_id}", prefix="edge"),
                    "source": source_node_id,
                    "target": page_node_id,
                    "type": "hierarchy",
                }
            )

            outline = extract_page_outline(page_text, max_depth=max_depth)
            if not outline:
                for idx, sentence in enumerate(first_sentences(page_text, limit=3), start=1):
                    leaf_id = stable_id(f"{page_node_id}|s|{idx}|{sentence}", prefix="leaf")
                    nodes.append(
                        {
                            "id": leaf_id,
                            "title": truncate(sentence, 120),
                            "text": truncate(sentence, 220),
                            "source_id": source_id,
                            "source_name": source_name,
                            "page_ref": page_label or None,
                            "node_type": "excerpt",
                            "children": [],
                            "related": [],
                        }
                    )
                    page_node["children"].append(leaf_id)
                    edges.append(
                        {
                            "id": stable_id(f"{page_node_id}->{leaf_id}", prefix="edge"),
                            "source": page_node_id,
                            "target": leaf_id,
                            "type": "hierarchy",
                        }
                    )
                continue

            level_parent: dict[int, str] = {1: page_node_id}
            for idx, outline_row in enumerate(outline, start=1):
                level = max(1, min(max_depth, int(outline_row.get("level", 1) or 1)))
                parent_id = level_parent.get(max(1, level - 1), page_node_id)
                node_type = "bullet" if outline_row.get("kind") == "bullet" else "section"
                child_id = stable_id(
                    f"{page_node_id}|{idx}|{outline_row.get('title','')}",
                    prefix="sec",
                )
                nodes.append(
                    {
                        "id": child_id,
                        "title": truncate(outline_row.get("title", ""), 120),
                        "text": truncate(outline_row.get("title", ""), 220),
                        "source_id": source_id,
                        "source_name": source_name,
                        "page_ref": page_label or None,
                        "node_type": node_type,
                        "children": [],
                        "related": [],
                    }
                )
                edges.append(
                    {
                        "id": stable_id(f"{parent_id}->{child_id}", prefix="edge"),
                        "source": parent_id,
                        "target": child_id,
                        "type": "hierarchy",
                    }
                )
                for node in nodes:
                    if node["id"] == parent_id:
                        node.setdefault("children", []).append(child_id)
                        break
                level_parent[level] = child_id

    multimodal_nodes = extract_multimodal_nodes(records, max_nodes=24)
    id_to_node = {node["id"]: node for node in nodes}
    for asset in multimodal_nodes:
        if len(nodes) >= node_limit:
            break
        nodes.append(asset)
        source_id = asset.get("source_id", "")
        page_ref = coerce_page_label(asset.get("page_ref", ""))
        attach_target = ""
        for node in nodes:
            if node.get("node_type") == "page" and node.get("source_id") == source_id:
                if not page_ref or coerce_page_label(node.get("page_ref")) == page_ref:
                    attach_target = str(node.get("id", ""))
                    break
        if not attach_target:
            for node in nodes:
                if node.get("node_type") in {"source", "web_source"} and node.get("source_id") == source_id:
                    attach_target = str(node.get("id", ""))
                    break
        if attach_target:
            edges.append(
                {
                    "id": stable_id(f"{attach_target}->{asset['id']}", prefix="edge"),
                    "source": attach_target,
                    "target": asset["id"],
                    "type": "hierarchy",
                }
            )
            id_to_node.get(attach_target, {}).setdefault("children", []).append(asset["id"])

    if len(nodes) > node_limit:
        allowed_ids = {node["id"] for node in nodes[:node_limit]}
        nodes = [node for node in nodes if node["id"] in allowed_ids]
        edges = [
            edge
            for edge in edges
            if edge.get("source") in allowed_ids and edge.get("target") in allowed_ids
        ]

    context_nodes = _build_reasoning_context_nodes(nodes, question=question, answer_text=answer_text)

    map_kind = "tree"
    if website_source_count > 0 and pdf_source_count > 0:
        map_kind = "hybrid"
    elif website_source_count > 0 and pdf_source_count == 0:
        map_kind = "graph"
    if source_type_hint.lower() in {"web", "website", "graph"}:
        map_kind = "graph"
    if source_type_hint.lower() in {"pdf", "tree"}:
        map_kind = "tree"

    payload: dict[str, Any] = {
        "version": 1,
        "kind": map_kind,
        "title": map_title,
        "root_id": root_id,
        "nodes": nodes,
        "edges": edges,
        "settings": {
            "max_depth": max_depth,
            "include_reasoning_map": bool(include_reasoning_map),
            "focus": focus_payload,
        },
        "source_summary": {
            "source_count": len(source_groups),
            "pdf_sources": pdf_source_count,
            "website_sources": website_source_count,
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
        "created_at": utc_now_iso(),
    }
    if include_reasoning_map:
        payload["reasoning_map"] = build_reasoning_map(
            question=question,
            answer_text=answer_text,
            context_nodes=context_nodes,
        )
    return payload


def serialize_map_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

