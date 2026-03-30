from __future__ import annotations

from typing import Any


def selected_scope_file_ids(selected_payload: dict[str, Any]) -> list[str]:
    selected_ids: list[str] = []
    seen: set[str] = set()
    for payload in selected_payload.values():
        if not isinstance(payload, list) or len(payload) < 2:
            continue
        mode = str(payload[0] or "").strip().lower()
        if mode != "select":
            continue
        file_ids = payload[1] if isinstance(payload[1], list) else []
        for raw_file_id in file_ids:
            file_id = str(raw_file_id or "").strip()
            if not file_id or file_id in seen:
                continue
            seen.add(file_id)
            selected_ids.append(file_id)
    return selected_ids


def build_sources_used(
    *,
    snippets_with_refs: list[dict[str, Any]],
    refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    candidates = list(snippets_with_refs) + list(refs)
    for row in candidates:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("file_id") or row.get("source_id") or "").strip()
        source_name = (
            str(row.get("source_name") or row.get("label") or "Indexed source").strip()
            or "Indexed source"
        )
        source_url = str(
            row.get("source_url") or row.get("page_url") or row.get("url") or ""
        ).strip()
        source_key = source_id or source_url or source_name.lower()
        if not source_key or source_key in seen:
            continue
        seen.add(source_key)
        source_type = str(row.get("source_type", "") or "").strip().lower()
        if not source_type:
            source_type = (
                "web"
                if source_url.startswith(("http://", "https://"))
                else "file"
            )
        credibility_tier = str(row.get("credibility_tier", "") or "").strip().lower() or None
        rows.append(
            {
                "source_type": source_type,
                "label": source_name,
                "url": source_url or None,
                "file_id": source_id or None,
                "score": row.get("strength_score") or row.get("score"),
                "credibility_tier": credibility_tier,
                "metadata": {
                    "page_label": str(row.get("page_label", "") or "").strip()
                    or None,
                    "unit_id": str(row.get("unit_id", "") or "").strip() or None,
                },
            }
        )
    return rows


def derive_rag_canvas_title(question: str, answer: str) -> str:
    first_heading = ""
    for line in str(answer or "").splitlines():
        candidate = str(line or "").strip()
        if not candidate:
            continue
        if candidate.startswith("#"):
            first_heading = candidate.lstrip("#").strip()
            break
        if len(candidate) > 24:
            break
    if first_heading:
        return first_heading[:140]
    normalized_question = str(question or "").strip().rstrip("?.! ")
    if normalized_question:
        return normalized_question[:140]
    return "RAG workspace draft"
