from __future__ import annotations

import math
import re
from typing import Any

from .extractors import (
    clean_text,
    coerce_page_label,
    first_sentences,
    jaccard,
    stable_id,
    tokenize,
    truncate,
)


_GENERIC_PAGE_TITLE_RE = re.compile(r"^(?:page|p)\s*\.?\s*\d+\s*$", re.IGNORECASE)
_CODE_LIKE_RE = re.compile(
    r"(->|=>|::|[{}\[\]<>]|`|\b(?:const|let|var|function|class|def|return|import|export|while|for)\b)",
    re.IGNORECASE,
)
_TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
    "within",
    "without",
    "must",
    "should",
    "can",
    "will",
    "this",
    "these",
    "those",
}


def map_kind_from_sources(
    *,
    source_type_hint: str,
    website_source_count: int,
    pdf_source_count: int,
) -> str:
    map_kind = "tree"
    if website_source_count > 0 and pdf_source_count > 0:
        map_kind = "hybrid"
    elif website_source_count > 0 and pdf_source_count == 0:
        map_kind = "graph"
    if source_type_hint.lower() in {"web", "website", "graph"}:
        return "graph"
    if source_type_hint.lower() in {"pdf", "tree"}:
        return "tree"
    return map_kind


def _is_generic_page_title(value: str) -> bool:
    cleaned = clean_text(value)
    if not cleaned:
        return True
    return bool(_GENERIC_PAGE_TITLE_RE.match(cleaned))


def _looks_code_like(value: str) -> bool:
    cleaned = clean_text(value)
    if not cleaned:
        return False
    if _CODE_LIKE_RE.search(cleaned):
        return True
    symbols = len(re.findall(r"[=><{}\[\]|`~$]", cleaned))
    alpha = len(re.findall(r"[A-Za-z]", cleaned))
    if alpha == 0:
        return True
    return (symbols / float(max(1, len(cleaned)))) > 0.055


def _token_to_title_word(token: str) -> str:
    lowered = token.lower()
    if len(token) <= 4 and token.isupper():
        return token
    return lowered.capitalize()


def _to_human_title(value: str, *, max_words: int = 6) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    cleaned = re.sub(r"^[a-zA-Z0-9_]{1,18}\s*:\s*", "", cleaned)
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"['\"`]", "", cleaned)
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]{1,}", cleaned)
    if not tokens:
        return ""
    picked: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        lowered = token.lower()
        if lowered in seen:
            continue
        if lowered in _TITLE_STOPWORDS:
            continue
        if len(lowered) <= 2:
            continue
        seen.add(lowered)
        picked.append(_token_to_title_word(token))
        if len(picked) >= max_words:
            break
    if len(picked) < 2:
        return ""
    return " ".join(picked)


def _clean_title_candidate(value: str) -> str:
    cleaned = clean_text(value).strip(" .,:;-")
    if not cleaned:
        return ""
    if _is_generic_page_title(cleaned):
        return ""
    if _looks_code_like(cleaned):
        return ""
    if len(cleaned) <= 74 and 2 <= len(re.findall(r"[A-Za-z0-9]+", cleaned)) <= 12:
        return truncate(cleaned, 88)
    return truncate(_to_human_title(cleaned) or cleaned, 88)


def derive_page_title(
    *,
    page_rows: list[dict[str, Any]],
    page_text: str,
    page_label: str,
    outline_rows: list[dict[str, Any]],
) -> str:
    metadata_keys = (
        "section_title",
        "heading",
        "chunk_title",
        "title",
        "subtitle",
        "h1",
        "h2",
    )

    for row in page_rows:
        metadata = row.get("metadata")
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        for key in metadata_keys:
            candidate = _clean_title_candidate(str(metadata_dict.get(key, "")))
            if candidate:
                return candidate

    for outline_row in outline_rows:
        candidate = _clean_title_candidate(str(outline_row.get("title", "")))
        if candidate:
            return candidate

    lines = [clean_text(line) for line in str(page_text or "").splitlines() if clean_text(line)]
    ranked_lines: list[tuple[float, str]] = []
    for line in lines[:140]:
        if len(line) < 5 or len(line) > 96:
            continue
        if _looks_code_like(line):
            continue
        words = re.findall(r"[A-Za-z0-9]+", line)
        if len(words) < 2 or len(words) > 14:
            continue
        score = 0.0
        if 3 <= len(words) <= 8:
            score += 2.0
        score += min(3.0, sum(1 for word in words if word[:1].isupper()) * 0.45)
        if ":" in line:
            score -= 0.4
        ranked_lines.append((score, line))
    ranked_lines.sort(key=lambda row: row[0], reverse=True)
    for _, line in ranked_lines[:6]:
        candidate = _clean_title_candidate(line)
        if candidate:
            return candidate

    for sentence in first_sentences(page_text, limit=3):
        cleaned_sentence = clean_text(re.sub(r"^[\W_]+", "", sentence))
        candidate = _clean_title_candidate(cleaned_sentence)
        if candidate:
            return candidate
        fallback = _to_human_title(cleaned_sentence, max_words=5)
        if fallback:
            return truncate(fallback, 88)

    page_value = clean_text(page_label)
    if page_value:
        return truncate(page_value, 88)

    source_name = clean_text((page_rows[0] or {}).get("source_name", "")) if page_rows else ""
    if source_name:
        return truncate(source_name, 88)

    return truncate(clean_text(page_text), 88)


def _node_page_order(node: dict[str, Any]) -> tuple[int, str]:
    page_ref = coerce_page_label(node.get("page_ref") or node.get("page") or "")
    if page_ref:
        match = re.search(r"\d+", page_ref)
        if match:
            try:
                return (int(match.group(0)), page_ref)
            except Exception:
                pass
    return (10**9, clean_text(node.get("title", "")))


def _topic_title_from_cluster(cluster_nodes: list[dict[str, Any]]) -> str:
    counts: dict[str, float] = {}
    representative = ""
    for node in cluster_nodes:
        node_title = clean_text(node.get("title", ""))
        if not representative and node_title:
            representative = node_title
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]{1,}", node_title):
            lowered = token.lower()
            if lowered in _TITLE_STOPWORDS or len(lowered) <= 2:
                continue
            counts[lowered] = counts.get(lowered, 0.0) + 2.0
        sentence_rows = first_sentences(node.get("text", ""), limit=1)
        sentence = clean_text(sentence_rows[0]) if sentence_rows else ""
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]{1,}", sentence):
            lowered = token.lower()
            if lowered in _TITLE_STOPWORDS or len(lowered) <= 2:
                continue
            counts[lowered] = counts.get(lowered, 0.0) + 1.0

    weighted = sorted(counts.items(), key=lambda row: (-row[1], row[0]))
    words = [_token_to_title_word(token) for token, _ in weighted[:6]]
    if len(words) >= 2:
        return " ".join(words[:6])
    candidate = _clean_title_candidate(representative)
    if candidate:
        return truncate(candidate, 80)
    merged = " ".join(clean_text(node.get("text", "")) for node in cluster_nodes[:3])
    fallback = _to_human_title(merged, max_words=6)
    if fallback:
        return truncate(fallback, 80)
    return truncate(clean_text(representative or cluster_nodes[0].get("id", "")), 80)


def _cluster_page_nodes(
    page_nodes: list[dict[str, Any]],
    *,
    max_topics: int = 7,
) -> list[list[dict[str, Any]]]:
    if len(page_nodes) < 7:
        return []

    ordered_nodes = sorted(page_nodes, key=_node_page_order)
    target_topics = max(3, min(max_topics, int(round(math.sqrt(len(ordered_nodes)))) + 1))

    clusters: list[dict[str, Any]] = []
    for order, node in enumerate(ordered_nodes):
        token_set = tokenize(f"{node.get('title', '')} {node.get('text', '')}")
        if not token_set:
            token_set = tokenize(node.get("title", ""))
        best_index = -1
        best_score = -1.0
        for index, cluster in enumerate(clusters):
            score = jaccard(token_set, cluster["centroid"])
            if score > best_score:
                best_score = score
                best_index = index
        threshold = 0.16 if len(token_set) >= 3 else 0.1
        if best_index >= 0 and (best_score >= threshold or len(clusters) >= target_topics):
            cluster = clusters[best_index]
            cluster["items"].append(node)
            cluster["tokens"].append(token_set)
            cluster["centroid"] = cluster["centroid"] | token_set
            cluster["first_order"] = min(cluster["first_order"], order)
            continue
        clusters.append(
            {
                "items": [node],
                "tokens": [token_set],
                "centroid": set(token_set),
                "first_order": order,
            }
        )

    while len(clusters) > 2:
        tiny_index = next((idx for idx, cluster in enumerate(clusters) if len(cluster["items"]) == 1), -1)
        if tiny_index < 0:
            break
        if len(clusters) <= target_topics:
            break
        tiny_cluster = clusters[tiny_index]
        tiny_tokens = tiny_cluster["tokens"][0]
        best_index = -1
        best_score = -1.0
        for index, cluster in enumerate(clusters):
            if index == tiny_index:
                continue
            score = jaccard(tiny_tokens, cluster["centroid"])
            if score > best_score:
                best_score = score
                best_index = index
        if best_index < 0:
            break
        merge_target = clusters[best_index]
        merge_target["items"].extend(tiny_cluster["items"])
        merge_target["tokens"].extend(tiny_cluster["tokens"])
        merge_target["centroid"] = merge_target["centroid"] | tiny_tokens
        merge_target["first_order"] = min(merge_target["first_order"], tiny_cluster["first_order"])
        clusters.pop(tiny_index)

    if len(clusters) < 2:
        bucket_count = max(3, min(max_topics, int(round(math.sqrt(len(ordered_nodes))))))
        bucket_size = max(1, int(math.ceil(len(ordered_nodes) / float(bucket_count))))
        buckets = [
            ordered_nodes[start : start + bucket_size]
            for start in range(0, len(ordered_nodes), bucket_size)
        ]
        if len(buckets) >= 2:
            return [bucket for bucket in buckets if bucket]

    clusters.sort(key=lambda row: row["first_order"])
    return [list(cluster["items"]) for cluster in clusters if cluster.get("items")]


def inject_topic_nodes(
    *,
    source_node: dict[str, Any],
    source_node_id: str,
    source_id: str,
    source_name: str,
    source_url: str,
    page_node_ids: list[str],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> int:
    if len(page_node_ids) < 7:
        return 0

    node_by_id = {str(node.get("id", "")): node for node in nodes}
    page_nodes = [
        node_by_id[node_id]
        for node_id in page_node_ids
        if isinstance(node_by_id.get(node_id), dict)
        and str(node_by_id[node_id].get("node_type", "")) == "page"
    ]
    if len(page_nodes) < 7:
        return 0

    clusters = _cluster_page_nodes(page_nodes)
    if len(clusters) < 2:
        return 0

    page_id_set = {node["id"] for node in page_nodes}
    filtered_edges = [
        edge
        for edge in edges
        if not (
            str(edge.get("type", "")) == "hierarchy"
            and str(edge.get("source", "")) == source_node_id
            and str(edge.get("target", "")) in page_id_set
        )
    ]
    edges[:] = filtered_edges

    source_children = [child for child in source_node.get("children", []) if child not in page_id_set]
    topic_ids: list[str] = []
    used_titles: set[str] = set()
    for index, cluster_nodes in enumerate(clusters, start=1):
        cluster_page_ids = [str(node.get("id", "")) for node in cluster_nodes if str(node.get("id", ""))]
        if not cluster_page_ids:
            continue
        cluster_title = _topic_title_from_cluster(cluster_nodes)
        normalized_title = clean_text(cluster_title).lower()
        if normalized_title in used_titles:
            page_refs = [
                coerce_page_label(node.get("page_ref") or node.get("page") or "")
                for node in sorted(cluster_nodes, key=_node_page_order)
            ]
            page_refs = [value for value in page_refs if value]
            if page_refs:
                first_ref = page_refs[0]
                last_ref = page_refs[-1]
                page_hint = first_ref if first_ref == last_ref else f"{first_ref}-{last_ref}"
                cluster_title = truncate(f"{cluster_title} {page_hint}", 80)
                normalized_title = clean_text(cluster_title).lower()
        used_titles.add(normalized_title)
        cluster_text = " ".join(clean_text(node.get("text", "")) for node in cluster_nodes[:3])
        topic_id = stable_id(
            f"{source_node_id}|topic|{index}|{'|'.join(cluster_page_ids[:6])}",
            prefix="topic",
        )
        nodes.append(
            {
                "id": topic_id,
                "title": truncate(cluster_title, 80),
                "text": truncate(cluster_text, 220),
                "source_id": source_id,
                "source_name": source_name,
                "url": source_url or None,
                "node_type": "topic",
                "type": "structure",
                "children": cluster_page_ids,
                "related": [],
                "crossLinks": [],
            }
        )
        topic_ids.append(topic_id)
        edges.append(
            {
                "id": stable_id(f"{source_node_id}->{topic_id}", prefix="edge"),
                "source": source_node_id,
                "target": topic_id,
                "type": "hierarchy",
            }
        )
        for page_id in cluster_page_ids:
            edges.append(
                {
                    "id": stable_id(f"{topic_id}->{page_id}", prefix="edge"),
                    "source": topic_id,
                    "target": page_id,
                    "type": "hierarchy",
                }
            )

    if not topic_ids:
        return 0
    source_node["children"] = source_children + topic_ids
    return len(topic_ids)
