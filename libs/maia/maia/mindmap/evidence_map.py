from __future__ import annotations

import re
from typing import Any

from .extractors import (
    MAX_DEFAULT_NODES,
    clean_text,
    coerce_page_label,
    normalize_records,
    stable_id,
    tokenize,
    truncate,
    utc_now_iso,
)


def _sentence_claims(answer_text: str, *, limit: int = 8) -> list[str]:
    cleaned = " ".join(str(answer_text or "").split()).strip()
    if not cleaned:
        return []
    parts = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", cleaned) if segment.strip()]
    if not parts:
        parts = [cleaned]
    claims: list[str] = []
    for part in parts:
        value = truncate(part, 220)
        if not value:
            continue
        claims.append(value)
        if len(claims) >= max(1, limit):
            break
    return claims


def _score_claim_evidence(claim: str, row: dict[str, Any]) -> float:
    claim_tokens = tokenize(claim)
    row_tokens = tokenize(f"{row.get('text', '')} {row.get('source_name', '')}")
    if not claim_tokens or not row_tokens:
        return 0.0
    overlap = claim_tokens & row_tokens
    if not overlap:
        return 0.0
    lexical = float(len(overlap)) / float(max(1, len(claim_tokens)))
    retrieval = 0.0
    for key in ("rerank_score", "vector_score", "score", "llm_trulens_score"):
        try:
            retrieval = max(retrieval, float(row.get(key, 0.0) or 0.0))
        except Exception:
            continue
    if retrieval > 1.0:
        retrieval = min(1.0, retrieval / 100.0)
    return round(min(1.0, lexical * 0.8 + retrieval * 0.2), 4)


def build_evidence_map(
    *,
    question: str,
    context: str,
    documents: list[Any] | None = None,
    answer_text: str = "",
    max_depth: int = 3,
    focus: dict[str, Any] | None = None,
    node_limit: int = MAX_DEFAULT_NODES,
) -> dict[str, Any]:
    del max_depth
    node_limit = max(32, min(900, int(node_limit)))
    rows = normalize_records(documents)
    focus_payload = dict(focus or {})
    title = truncate(question or "Evidence map", 120) or "Evidence map"
    root_id = stable_id(title, prefix="root")
    root_node = {
        "id": root_id,
        "title": title,
        "text": truncate(context or answer_text, 240),
        "node_type": "root",
        "type": "evidence",
        "children": [],
        "crossLinks": [],
    }
    nodes: list[dict[str, Any]] = [root_node]
    edges: list[dict[str, Any]] = []

    claims = _sentence_claims(answer_text, limit=8)
    if not claims and question:
        claims = [truncate(question, 220)]

    source_nodes: dict[str, str] = {}
    for row in rows:
        source_id = str(row.get("source_id", "") or "")
        if not source_id or source_id in source_nodes:
            continue
        source_name = str(row.get("source_name", "Indexed source"))
        source_node_id = stable_id(f"{source_id}|{source_name}", prefix="src")
        source_nodes[source_id] = source_node_id
        nodes.append(
            {
                "id": source_node_id,
                "title": truncate(source_name, 120),
                "text": truncate(source_name, 220),
                "source_id": source_id,
                "source_name": source_name,
                "node_type": "source",
                "type": "evidence",
                "children": [],
                "crossLinks": [],
            }
        )
        root_node["children"].append(source_node_id)
        edges.append(
            {
                "id": stable_id(f"{root_id}->{source_node_id}", prefix="edge"),
                "source": root_id,
                "target": source_node_id,
                "type": "hierarchy",
            }
        )

    for claim_idx, claim in enumerate(claims, start=1):
        claim_id = stable_id(f"{title}|claim|{claim_idx}|{claim}", prefix="claim")
        nodes.append(
            {
                "id": claim_id,
                "title": f"Claim {claim_idx}",
                "text": claim,
                "node_type": "claim",
                "type": "evidence",
                "children": [],
                "crossLinks": [],
            }
        )
        root_node["children"].append(claim_id)
        edges.append(
            {
                "id": stable_id(f"{root_id}->{claim_id}", prefix="edge"),
                "source": root_id,
                "target": claim_id,
                "type": "hierarchy",
            }
        )

        scored_rows = sorted(
            (
                (_score_claim_evidence(claim, row), row)
                for row in rows
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        support_count = 0
        for score, row in scored_rows:
            if score <= 0.0:
                continue
            source_id = str(row.get("source_id", "") or "")
            source_node_id = source_nodes.get(source_id)
            if not source_node_id:
                continue
            page_label = coerce_page_label(row.get("page_label", ""))
            evidence_text = truncate(clean_text(row.get("text", "")), 260)
            if not evidence_text:
                continue
            evidence_id = stable_id(
                f"{claim_id}|{source_id}|{page_label}|{support_count}|{evidence_text}",
                prefix="ev",
            )
            nodes.append(
                {
                    "id": evidence_id,
                    "title": f"Evidence {support_count + 1}",
                    "text": evidence_text,
                    "source_id": source_id,
                    "source_name": row.get("source_name", "Indexed source"),
                    "page_ref": page_label or None,
                    "page": page_label or None,
                    "score": score,
                    "node_type": "evidence",
                    "type": "evidence",
                    "children": [],
                    "crossLinks": [],
                }
            )
            edges.append(
                {
                    "id": stable_id(f"{claim_id}->{evidence_id}", prefix="edge"),
                    "source": claim_id,
                    "target": evidence_id,
                    "type": "support",
                    "weight": score,
                }
            )
            edges.append(
                {
                    "id": stable_id(f"{source_node_id}->{evidence_id}", prefix="edge"),
                    "source": source_node_id,
                    "target": evidence_id,
                    "type": "reference",
                    "weight": score,
                }
            )
            support_count += 1
            if support_count >= 4:
                break
            if len(nodes) >= node_limit:
                break
        if len(nodes) >= node_limit:
            break

    if len(nodes) > node_limit:
        allowed_ids = {node["id"] for node in nodes[:node_limit]}
        nodes = [node for node in nodes if node.get("id") in allowed_ids]
        edges = [
            edge
            for edge in edges
            if edge.get("source") in allowed_ids and edge.get("target") in allowed_ids
        ]

    return {
        "version": 2,
        "map_type": "evidence",
        "kind": "graph",
        "title": title,
        "root_id": root_id,
        "nodes": nodes,
        "edges": edges,
        "settings": {
            "focus": focus_payload,
        },
        "source_summary": {
            "source_count": len(source_nodes),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "claim_count": len(claims),
        },
        "created_at": utc_now_iso(),
    }
