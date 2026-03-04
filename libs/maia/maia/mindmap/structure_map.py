from __future__ import annotations

import urllib.parse
from typing import Any

from .extractors import (
    MAX_DEFAULT_NODES,
    clean_text,
    coerce_page_label,
    extract_multimodal_nodes,
    extract_page_outline,
    first_sentences,
    group_records_by_source,
    jaccard,
    normalize_records,
    sort_page_key,
    stable_id,
    tokenize,
    truncate,
    utc_now_iso,
)
from .structure_helpers import derive_page_title, inject_topic_nodes, map_kind_from_sources


def build_structure_map(
    *,
    question: str,
    context: str,
    documents: list[Any] | None = None,
    max_depth: int = 4,
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
        "type": "structure",
        "children": [],
        "related": [],
        "crossLinks": [],
        "focus": bool(focus_payload),
    }
    nodes: list[dict[str, Any]] = [root_node]
    edges: list[dict[str, Any]] = []
    page_node_lookup: dict[tuple[str, str], str] = {}
    source_node_lookup: dict[str, str] = {}
    url_to_node_id: dict[str, str] = {}

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
    topic_cluster_count = 0

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
            "url": source_url or None,
            "node_type": "web_source" if is_web else "source",
            "type": "structure",
            "children": [],
            "related": [],
            "crossLinks": [],
        }
        nodes.append(source_node)
        source_node_lookup[source_id] = source_node_id
        if source_url:
            url_to_node_id[source_url.rstrip("/").lower()] = source_node_id
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
        source_page_node_ids: list[str] = []
        for row in rows:
            page_groups.setdefault(row.get("page_label", ""), []).append(row)
        sorted_pages = sorted(page_groups.keys(), key=sort_page_key) or [""]
        for page_label in sorted_pages:
            page_rows = page_groups.get(page_label, rows)
            page_node_id = stable_id(f"{source_node_id}|page|{page_label or 'na'}", prefix="page")
            page_text = " ".join(row.get("text", "") for row in page_rows[:4])
            outline = extract_page_outline(page_text, max_depth=max_depth)
            page_title = derive_page_title(
                page_rows=page_rows,
                page_text=page_text,
                page_label=page_label,
                outline_rows=outline,
            )
            page_node = {
                "id": page_node_id,
                "title": truncate(page_title, 80),
                "text": truncate(page_text, 240),
                "source_id": source_id,
                "source_name": source_name,
                "url": source_url or None,
                "page_ref": page_label or None,
                "page": coerce_page_label(page_label) or None,
                "node_type": "page",
                "type": "structure",
                "children": [],
                "related": [],
                "crossLinks": [],
            }
            nodes.append(page_node)
            page_node_lookup[(source_id, coerce_page_label(page_label))] = page_node_id
            source_node["children"].append(page_node_id)
            source_page_node_ids.append(page_node_id)
            edges.append(
                {
                    "id": stable_id(f"{source_node_id}->{page_node_id}", prefix="edge"),
                    "source": source_node_id,
                    "target": page_node_id,
                    "type": "hierarchy",
                }
            )

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
                            "page": coerce_page_label(page_label) or None,
                            "node_type": "excerpt",
                            "type": "structure",
                            "children": [],
                            "related": [],
                            "crossLinks": [],
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
                    f"{page_node_id}|{idx}|{outline_row.get('title', '')}",
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
                        "page": coerce_page_label(page_label) or None,
                        "node_type": node_type,
                        "type": "structure",
                        "children": [],
                        "related": [],
                        "crossLinks": [],
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

        topic_cluster_count += inject_topic_nodes(
            source_node=source_node,
            source_node_id=source_node_id,
            source_id=source_id,
            source_name=source_name,
            source_url=source_url,
            page_node_ids=source_page_node_ids,
            nodes=nodes,
            edges=edges,
        )

    multimodal_nodes = extract_multimodal_nodes(records, max_nodes=24)
    id_to_node = {node["id"]: node for node in nodes}
    for asset in multimodal_nodes:
        if len(nodes) >= node_limit:
            break
        asset["type"] = "structure"
        asset["crossLinks"] = []
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

    for row in records:
        source_id = str(row.get("source_id", ""))
        page_label = coerce_page_label(row.get("page_label"))
        from_node_id = page_node_lookup.get((source_id, page_label)) or source_node_lookup.get(source_id)
        if not from_node_id:
            continue
        row_url = clean_text(row.get("url", "")).rstrip("/").lower()
        if row_url and row_url not in url_to_node_id:
            url_to_node_id[row_url] = from_node_id

    existing_edge_pairs = {(str(edge.get("source", "")), str(edge.get("target", ""))) for edge in edges}
    for row in records:
        links = row.get("links", [])
        if not isinstance(links, list) or not links:
            continue
        source_id = str(row.get("source_id", ""))
        page_label = coerce_page_label(row.get("page_label"))
        from_node_id = page_node_lookup.get((source_id, page_label)) or source_node_lookup.get(source_id)
        if not from_node_id:
            continue
        row_url = clean_text(row.get("url", ""))
        for link in links[:24]:
            link_text = clean_text(link)
            if not link_text:
                continue
            normalized_link = urllib.parse.urljoin(row_url, link_text) if row_url else link_text
            normalized_link = normalized_link.split("#", 1)[0].rstrip("/").lower()
            target_node_id = url_to_node_id.get(normalized_link)
            if not target_node_id or target_node_id == from_node_id:
                continue
            pair = (from_node_id, target_node_id)
            if pair in existing_edge_pairs:
                continue
            existing_edge_pairs.add(pair)
            edges.append(
                {
                    "id": stable_id(f"{from_node_id}->{target_node_id}", prefix="edge"),
                    "source": from_node_id,
                    "target": target_node_id,
                    "type": "hyperlink",
                }
            )
            id_to_node.get(from_node_id, {}).setdefault("crossLinks", []).append(target_node_id)

    candidates = [node for node in nodes if node.get("node_type") not in {"root", "source", "web_source", "page"}]
    token_cache = {
        str(node.get("id", "")): tokenize(f"{node.get('title', '')} {node.get('text', '')}")
        for node in candidates[:160]
    }
    scored: list[tuple[float, str, str]] = []
    for idx, left in enumerate(candidates[:160]):
        left_id = str(left.get("id", ""))
        left_tokens = token_cache.get(left_id, set())
        if len(left_tokens) < 2:
            continue
        for right in candidates[idx + 1 : 160]:
            right_id = str(right.get("id", ""))
            if left_id == right_id:
                continue
            if str(left.get("source_id", "")) == str(right.get("source_id", "")):
                continue
            right_tokens = token_cache.get(right_id, set())
            if len(right_tokens) < 2:
                continue
            score = jaccard(left_tokens, right_tokens)
            if score >= 0.24:
                scored.append((score, left_id, right_id))
    scored.sort(key=lambda row: row[0], reverse=True)
    for score, left_id, right_id in scored[:80]:
        pair = (left_id, right_id)
        if pair in existing_edge_pairs:
            continue
        existing_edge_pairs.add(pair)
        edges.append(
            {
                "id": stable_id(f"{left_id}->{right_id}|{score:.3f}", prefix="edge"),
                "source": left_id,
                "target": right_id,
                "type": "reference",
                "weight": round(float(score), 3),
            }
        )
        id_to_node.get(left_id, {}).setdefault("crossLinks", []).append(right_id)

    if len(nodes) > node_limit:
        allowed_ids = {node["id"] for node in nodes[:node_limit]}
        nodes = [node for node in nodes if node.get("id") in allowed_ids]
        edges = [
            edge
            for edge in edges
            if edge.get("source") in allowed_ids and edge.get("target") in allowed_ids
        ]

    map_kind = map_kind_from_sources(
        source_type_hint=source_type_hint,
        website_source_count=website_source_count,
        pdf_source_count=pdf_source_count,
    )
    return {
        "version": 2,
        "map_type": "structure",
        "kind": map_kind,
        "title": map_title,
        "root_id": root_id,
        "nodes": nodes,
        "edges": edges,
        "settings": {
            "max_depth": max_depth,
            "focus": focus_payload,
            "source_type_hint": source_type_hint,
        },
        "source_summary": {
            "source_count": len(source_groups),
            "pdf_sources": pdf_source_count,
            "website_sources": website_source_count,
            "topic_clusters": topic_cluster_count,
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
        "created_at": utc_now_iso(),
    }
