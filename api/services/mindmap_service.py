from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from maia.mindmap.indexer import build_knowledge_map

if TYPE_CHECKING:
    from api.context import ApiContext

from .mindmap_service_helpers import (
    build_tree_view,
    classify_source_type,
    compact_text,
    load_source_documents,
    normalize_map_type,
    phase_label,
    phase_status,
    source_hint,
    work_graph_action_node_type,
    work_graph_action_status,
)


def _normalize_map_type(raw: str) -> str:
    return normalize_map_type(raw)


def build_agent_work_graph(
    *,
    request_message: str,
    actions_taken: list[dict[str, Any]] | None,
    sources_used: list[dict[str, Any]] | None = None,
    map_type: str = "work_graph",
    max_depth: int = 4,
    run_id: str = "",
) -> dict[str, Any]:
    """Build a properly branched mindmap tree — not a linear chain.

    Structure (NotebookLM-style):
        root
        ├── Planning          (action phase branch)
        │   ├── step_1
        │   └── step_2
        ├── Research          (action phase branch)
        │   └── step_3
        ├── Evidence Found    (source branch)
        │   ├── source_1
        │   └── source_2
        └── Verification      (summary branch)

    Context mindmap groups sources by type (Web Research / Documents / Other).
    """
    map_type_norm = normalize_map_type(map_type)
    clipped_depth = max(2, min(8, int(max_depth)))
    max_steps = max(6, min(64, clipped_depth * 10))
    root_id = f"task_{str(run_id).strip()}" if str(run_id).strip() else "task_root"
    root_title = compact_text(request_message or "Agent execution", max_len=120)

    action_rows = actions_taken if isinstance(actions_taken, list) else []
    source_rows = sources_used if isinstance(sources_used, list) else []

    # ── Pre-process action rows into phase groups ─────────────────────────────
    # Phase order determines branch order in the mindmap
    phase_order = ["plan_step", "research", "email_draft", "api_operation"]
    phase_items: dict[str, list[tuple[int, dict[str, Any]]]] = {k: [] for k in phase_order}
    success_count = 0
    failed_count = 0

    for index, row in enumerate(action_rows[:max_steps], start=1):
        if not isinstance(row, dict):
            continue
        raw_status = str(row.get("status", "") or "")
        status = work_graph_action_status(raw_status)
        if status == "completed":
            success_count += 1
        if status == "failed":
            failed_count += 1
        node_type = work_graph_action_node_type(row)
        phase_items.setdefault(node_type, []).append((index, row))

    # ── Build WORK GRAPH payload (branched by execution phase) ────────────────
    wg_nodes: list[dict[str, Any]] = [
        {
            "id": root_id,
            "title": root_title or "Agent execution",
            "text": "Execution plan and runtime outcomes",
            "node_type": "task",
            "status": "active",
            "confidence": 0.9,
        }
    ]
    wg_edges: list[dict[str, Any]] = []

    for phase_key in phase_order:
        items = phase_items.get(phase_key, [])
        if not items:
            continue
        phase_id = f"phase_{phase_key}"
        label = phase_label(phase_key)
        statuses = [work_graph_action_status(str(r.get("status", "") or "")) for _, r in items]
        wg_nodes.append(
            {
                "id": phase_id,
                "title": label,
                "text": f"{len(items)} step(s)",
                "node_type": "phase",
                "status": phase_status(statuses),
                "confidence": 0.85,
            }
        )
        wg_edges.append(
            {"id": f"{root_id}->{phase_id}", "source": root_id, "target": phase_id, "type": "hierarchy", "edge_family": "hierarchy"}
        )
        for index, row in items:
            action_id = f"action_{index}"
            raw_status = str(row.get("status", "") or "")
            status = work_graph_action_status(raw_status)
            tool_id = compact_text(row.get("tool_id", ""), max_len=120)
            summary = compact_text(row.get("summary", ""), max_len=160) or tool_id or f"Step {index}"
            action_class = compact_text(row.get("action_class", ""), max_len=40) or "execute"
            confidence = 0.9 if status == "completed" else 0.35 if status == "failed" else 0.55
            wg_nodes.append(
                {
                    "id": action_id,
                    "title": summary,
                    "text": f"{action_class} via {tool_id or 'runtime tool'}",
                    "node_type": phase_key,
                    "status": status,
                    "confidence": confidence,
                    "tool_id": tool_id,
                    "action_class": action_class,
                    "started_at": str(row.get("started_at", "") or ""),
                    "ended_at": str(row.get("ended_at", "") or ""),
                }
            )
            wg_edges.append(
                {"id": f"{phase_id}->{action_id}", "source": phase_id, "target": action_id, "type": "hierarchy", "edge_family": "sequential"}
            )

    # Evidence branch (direct child of root, not chained after last step)
    if source_rows:
        ev_branch_id = "branch_evidence"
        wg_nodes.append(
            {
                "id": ev_branch_id,
                "title": "Evidence Found",
                "text": f"{min(len(source_rows), 24)} source(s)",
                "node_type": "phase",
                "status": "completed",
                "confidence": 0.9,
            }
        )
        wg_edges.append(
            {"id": f"{root_id}->{ev_branch_id}", "source": root_id, "target": ev_branch_id, "type": "hierarchy", "edge_family": "evidence"}
        )
        for si, row in enumerate(source_rows[:24], start=1):
            if not isinstance(row, dict):
                continue
            node_id = f"evidence_{si}"
            source_label = compact_text(
                row.get("label") or row.get("url") or row.get("file_id") or f"Evidence {si}", max_len=120
            )
            wg_nodes.append(
                {
                    "id": node_id,
                    "title": source_label,
                    "text": compact_text(row.get("source_type"), max_len=80) or "source",
                    "node_type": "artifact",
                    "status": "completed",
                    "source_type": str(row.get("source_type", "") or ""),
                    "url": str(row.get("url", "") or ""),
                    "file_id": str(row.get("file_id", "") or ""),
                }
            )
            wg_edges.append(
                {"id": f"{ev_branch_id}->{node_id}", "source": ev_branch_id, "target": node_id, "type": "hierarchy", "edge_family": "evidence"}
            )

    # Verification branch (direct child of root)
    total_actions = max(1, success_count + failed_count)
    verification_status = "failed" if failed_count > 0 else "completed"
    ver_id = "verification_summary"
    wg_nodes.append(
        {
            "id": ver_id,
            "title": "Verification",
            "text": f"{success_count} succeeded, {failed_count} failed",
            "node_type": "verification",
            "status": verification_status,
            "confidence": round(success_count / total_actions, 2),
        }
    )
    wg_edges.append(
        {"id": f"{root_id}->{ver_id}", "source": root_id, "target": ver_id, "type": "hierarchy", "edge_family": "verification"}
    )

    # ── Build CONTEXT MINDMAP payload (branched by source type) ──────────────
    cm_nodes: list[dict[str, Any]] = [
        {
            "id": root_id,
            "title": root_title or "Research context",
            "text": "Answer context and evidence sources",
            "node_type": "task",
            "status": "active",
            "confidence": 0.9,
        }
    ]
    cm_edges: list[dict[str, Any]] = []

    if source_rows:
        # Group sources into at most 3 type buckets
        web_sources = [r for r in source_rows[:32] if isinstance(r, dict) and classify_source_type(r) == "web"]
        doc_sources = [r for r in source_rows[:32] if isinstance(r, dict) and classify_source_type(r) == "doc"]
        other_sources = [r for r in source_rows[:32] if isinstance(r, dict) and classify_source_type(r) == "other"]

        def _add_cm_branch(
            branch_id: str, branch_title: str, rows: list[dict[str, Any]], prefix: str
        ) -> None:
            cm_nodes.append(
                {
                    "id": branch_id,
                    "title": branch_title,
                    "text": f"{len(rows)} source(s)",
                    "node_type": "source_group",
                    "status": "completed",
                    "confidence": 0.9,
                }
            )
            cm_edges.append(
                {"id": f"{root_id}->{branch_id}", "source": root_id, "target": branch_id, "type": "hierarchy", "edge_family": "evidence"}
            )
            for si, row in enumerate(rows, start=1):
                node_id = f"{prefix}_{si}"
                source_label = compact_text(
                    row.get("label") or row.get("url") or row.get("file_id") or f"Source {si}", max_len=120
                )
                cm_nodes.append(
                    {
                        "id": node_id,
                        "title": source_label,
                        "text": compact_text(row.get("source_type"), max_len=80) or "source",
                        "node_type": "source",
                        "status": "completed",
                        "source_type": str(row.get("source_type", "") or ""),
                        "url": str(row.get("url", "") or ""),
                        "file_id": str(row.get("file_id", "") or ""),
                    }
                )
                cm_edges.append(
                    {"id": f"{branch_id}->{node_id}", "source": branch_id, "target": node_id, "type": "hierarchy", "edge_family": "evidence"}
                )

        if web_sources:
            _add_cm_branch("branch_web", "Web Research", web_sources, "web")
        if doc_sources:
            _add_cm_branch("branch_docs", "Documents", doc_sources, "doc")
        if other_sources:
            _add_cm_branch("branch_other", "Other Sources", other_sources, "oth")

    else:
        # No sources — fall back to phase-grouped action steps
        for phase_key in phase_order:
            items = phase_items.get(phase_key, [])
            if not items:
                continue
            branch_id = f"cm_phase_{phase_key}"
            cm_nodes.append(
                {
                    "id": branch_id,
                    "title": phase_label(phase_key),
                    "text": f"{len(items)} step(s)",
                    "node_type": "source_group",
                    "status": "completed",
                }
            )
            cm_edges.append(
                {"id": f"{root_id}->{branch_id}", "source": root_id, "target": branch_id, "type": "hierarchy", "edge_family": "sequential"}
            )
            for index, row in items[:8]:
                node_id = f"cm_action_{index}"
                summary = compact_text(
                    row.get("summary") or row.get("tool_id") or f"Step {index}", max_len=140
                )
                cm_nodes.append(
                    {"id": node_id, "title": summary, "text": "Execution step", "node_type": "plan_step", "status": "completed"}
                )
                cm_edges.append(
                    {"id": f"{branch_id}->{node_id}", "source": branch_id, "target": node_id, "type": "hierarchy", "edge_family": "sequential"}
                )

    # ── Assemble final payloads ────────────────────────────────────────────────
    base_payload: dict[str, Any] = {
        "version": 2,
        "map_type": "work_graph",
        "kind": "work_graph",
        "title": f"Work graph — {root_title or 'Agent execution'}",
        "root_id": root_id,
        "nodes": wg_nodes,
        "edges": wg_edges,
        "graph": {
            "schema": "work_graph.v1",
            "run_id": str(run_id or ""),
            "action_count": len(action_rows),
            "source_count": len(source_rows),
        },
        "settings": {"map_type": "work_graph", "graph_mode": "execution"},
    }
    base_payload["tree"] = build_tree_view(base_payload)

    context_payload: dict[str, Any] = {
        "version": 2,
        "map_type": "context_mindmap",
        "kind": "context_mindmap",
        "title": f"Research map — {root_title or 'Agent execution'}",
        "root_id": root_id,
        "nodes": cm_nodes,
        "edges": cm_edges,
        "graph": {
            "schema": "context_mindmap.v1",
            "run_id": str(run_id or ""),
            "source_count": len(source_rows),
        },
        "settings": {"map_type": "context_mindmap", "graph_mode": "context"},
    }
    context_payload["tree"] = build_tree_view(context_payload)

    variants: dict[str, dict[str, Any]] = {}
    variants["work_graph"] = base_payload
    for variant_key, kind in (
        ("context_mindmap", "context_mindmap"),
        ("structure", "graph"),
        ("evidence", "graph"),
    ):
        variant_payload = {**context_payload, "map_type": variant_key, "kind": kind}
        variant_payload["tree"] = build_tree_view(variant_payload)
        variants[variant_key] = variant_payload

    selected_payload = dict(variants.get(map_type_norm, variants["context_mindmap"]))
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
    source_name, documents = load_source_documents(
        context=context,
        user_id=user_id,
        source_id=source_id,
    )
    if not documents:
        raise HTTPException(status_code=404, detail="No indexed chunks found for this source.")

    map_type_norm = normalize_map_type(map_type)
    build_map_type = "structure" if map_type_norm == "context_mindmap" else map_type_norm
    clipped_depth = max(2, min(8, int(max_depth)))
    map_title = f"Map for {source_name}"
    context_preview = "\n\n".join(str(row.get("text", "") or "") for row in documents[:8])
    payload = build_knowledge_map(
        question=map_title,
        context=context_preview,
        documents=documents,
        answer_text="",
        max_depth=clipped_depth,
        include_reasoning_map=bool(include_reasoning_map),
        source_type_hint=source_hint(source_name),
        focus={"source_id": source_id, "source_name": source_name},
        map_type=build_map_type,
    )
    if map_type_norm != "context_mindmap":
        return payload

    normalized = dict(payload)
    normalized["map_type"] = "context_mindmap"
    normalized["kind"] = "context_mindmap"
    settings = normalized.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings["map_type"] = "context_mindmap"
    normalized["settings"] = settings
    variants = normalized.get("variants")
    if isinstance(variants, dict):
        context_variant = dict(variants.get("structure") or normalized)
        context_variant["map_type"] = "context_mindmap"
        context_variant["kind"] = "context_mindmap"
        variants["context_mindmap"] = context_variant
        normalized["variants"] = variants
    return normalized


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
