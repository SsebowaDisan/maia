from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from maia.mindmap.indexer import build_knowledge_map

# Matches [1], [12], 【1】, {1} style inline citation markers
_INLINE_REF_RE = re.compile(r"[\[\u3010\uff3b\{]\s*(\d{1,4})\s*[\]\u3011\uff3d\}]")
# Splits answer text into sentences (keeps the delimiter)
_SENTENCE_SPLIT_RE = re.compile(r"[^.!?\n]+(?:[.!?\n]+|$)")

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


def _generate_reasoning_steps_llm(answer_text: str, question: str) -> list[str]:
    """Ask the LLM to extract 3-5 key reasoning steps from the answer text.

    Returns an empty list on any error so callers always fall back to the
    indexer's built-in template when this function fails or the LLM is
    unavailable.
    """
    try:
        import json as _json
        from decouple import config as _decouple_config
        from ktem.llms.manager import llms as _llms
        from .chat.pipeline import is_placeholder_api_key as _is_placeholder
        from .chat.fast_qa_runtime_helpers import (
            call_openai_chat_text as _call_llm,
            extract_text_content as _extract_text,
            resolve_fast_qa_llm_config as _resolve_config,
        )

        api_key, base_url, model, _ = _resolve_config(
            config_fn=_decouple_config,
            is_placeholder_api_key_fn=_is_placeholder,
            llms_manager=_llms,
        )
        if not api_key:
            return []

        q_preview = (question or "")[:400]
        a_preview = (answer_text or "")[:800]
        prompt = (
            "You are a reasoning analyst. Identify 3 to 5 key reasoning steps "
            "used to answer the following question based on the answer excerpt.\n\n"
            f"Question: {q_preview}\n\n"
            f"Answer excerpt: {a_preview}\n\n"
            "Return ONLY a JSON array of short strings (10–60 words each). "
            'Example: ["Identify key sources", "Extract supporting evidence", "Synthesise findings"]'
        )
        raw = _call_llm(
            api_key=api_key,
            base_url=base_url,
            request_payload={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 400,
            },
            timeout_seconds=12,
            extract_text_content_fn=_extract_text,
        )
        if not raw:
            return []
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text.strip())
        parsed = _json.loads(text)
        if isinstance(parsed, list):
            return [str(s).strip() for s in parsed if str(s).strip()][:5]
        return []
    except Exception:
        return []


def _build_reasoning_map(
    answer_text: str,
    source_node_ids: dict[int, str],
) -> dict[str, Any]:
    """Extract cited sentences from answer_text and build a claim→evidence graph.

    Returns a reasoning_map dict with layout, nodes, and edges matching the
    ReasoningNode / ReasoningEdge frontend types.
    """
    r_nodes: list[dict[str, Any]] = []
    r_edges: list[dict[str, Any]] = []
    seen_claim_ids: set[str] = set()

    for sentence in _SENTENCE_SPLIT_RE.findall(answer_text.strip()):
        ref_matches = _INLINE_REF_RE.findall(sentence)
        if not ref_matches:
            continue
        clean = " ".join(sentence.split()).strip()
        if len(clean) < 20:
            continue
        # Stable ID: FNV-like hash of the sentence text (avoids uuid import)
        claim_id = f"claim_{abs(hash(clean)) % 1_000_000}"
        if claim_id not in seen_claim_ids:
            seen_claim_ids.add(claim_id)
            r_nodes.append(
                {
                    "id": claim_id,
                    "label": compact_text(clean, max_len=140),
                    "kind": "claim",
                }
            )
        for ref_str in ref_matches:
            ref_num = int(ref_str)
            ev_node_id = source_node_ids.get(ref_num)
            if ev_node_id:
                edge_id = f"{claim_id}->{ev_node_id}"
                r_edges.append({"id": edge_id, "source": claim_id, "target": ev_node_id})

    return {"layout": "force", "nodes": r_nodes, "edges": r_edges}


def _build_evidence_variant(
    root_id: str,
    root_title: str,
    answer_text: str,
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build an evidence map variant as a proper claim→source graph.

    Nodes: root task, claim sentences (from answer [n] citations), source artifacts.
    Edges: root→claim, claim→source (by citation number).
    Falls back to root→source direct edges when no answer citations are available.
    """
    ev_nodes: list[dict[str, Any]] = [
        {
            "id": root_id,
            "title": root_title or "Research",
            "text": "Claims and supporting evidence",
            "node_type": "task",
            "status": "active",
            "confidence": 0.9,
        }
    ]
    ev_edges: list[dict[str, Any]] = []

    # Build source artifact nodes (1-indexed to align with [n] citation markers)
    source_node_ids: dict[int, str] = {}
    for si, row in enumerate(source_rows[:24], start=1):
        if not isinstance(row, dict):
            continue
        src_id = f"ev_src_{si}"
        source_node_ids[si] = src_id
        label = compact_text(
            row.get("label") or row.get("url") or row.get("file_id") or f"Source {si}",
            max_len=120,
        )
        ev_nodes.append(
            {
                "id": src_id,
                "title": label,
                "text": compact_text(row.get("source_type"), max_len=80) or "source",
                "node_type": "artifact",
                "status": "completed",
                "source_type": str(row.get("source_type", "") or ""),
                "url": str(row.get("url", "") or ""),
                "file_id": str(row.get("file_id", "") or ""),
            }
        )

    claim_count = 0
    seen_claim_ids: set[str] = set()
    used_src_ids: set[str] = set()

    if answer_text.strip():
        for sentence in _SENTENCE_SPLIT_RE.findall(answer_text.strip()):
            ref_matches = _INLINE_REF_RE.findall(sentence)
            valid_refs = [int(m) for m in ref_matches if int(m) in source_node_ids]
            if not valid_refs:
                continue
            clean = " ".join(sentence.split()).strip()
            if len(clean) < 20:
                continue
            claim_id = f"ev_claim_{abs(hash(clean)) % 1_000_000}"
            if claim_id not in seen_claim_ids:
                seen_claim_ids.add(claim_id)
                claim_count += 1
                ev_nodes.append(
                    {
                        "id": claim_id,
                        "title": compact_text(clean, max_len=140),
                        "text": "Cited claim",
                        "node_type": "plan_step",
                        "status": "completed",
                    }
                )
                ev_edges.append(
                    {
                        "id": f"{root_id}->{claim_id}",
                        "source": root_id,
                        "target": claim_id,
                        "type": "hierarchy",
                    }
                )
            for ref_num in valid_refs:
                src_node_id = source_node_ids[ref_num]
                used_src_ids.add(src_node_id)
                edge_id = f"{claim_id}->{src_node_id}"
                if not any(e.get("id") == edge_id for e in ev_edges):
                    ev_edges.append(
                        {
                            "id": edge_id,
                            "source": claim_id,
                            "target": src_node_id,
                            "type": "hierarchy",
                        }
                    )

    # Fall back to direct root→source edges when no claims were extracted
    if claim_count == 0:
        for src_node_id in source_node_ids.values():
            ev_edges.append(
                {
                    "id": f"{root_id}->{src_node_id}",
                    "source": root_id,
                    "target": src_node_id,
                    "type": "hierarchy",
                }
            )

    return {"nodes": ev_nodes, "edges": ev_edges}


def build_agent_work_graph(
    *,
    request_message: str,
    actions_taken: list[dict[str, Any]] | None,
    sources_used: list[dict[str, Any]] | None = None,
    answer_text: str = "",
    map_type: str = "work_graph",
    max_depth: int = 4,
    include_reasoning_map: bool = False,
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

    # ── Build EVIDENCE VARIANT (claim→source graph) ───────────────────────────
    ev_data = _build_evidence_variant(
        root_id=root_id,
        root_title=root_title,
        answer_text=answer_text,
        source_rows=source_rows,
    )
    evidence_payload: dict[str, Any] = {
        "version": 2,
        "map_type": "evidence",
        "kind": "evidence",
        "title": f"Evidence map — {root_title or 'Agent execution'}",
        "root_id": root_id,
        "nodes": ev_data["nodes"],
        "edges": ev_data["edges"],
        "graph": {
            "schema": "evidence.v1",
            "run_id": str(run_id or ""),
            "source_count": len(source_rows),
        },
        "settings": {"map_type": "evidence", "graph_mode": "evidence"},
    }
    evidence_payload["tree"] = build_tree_view(evidence_payload)

    # structure variant reuses the work-graph hierarchy (execution structure)
    structure_payload: dict[str, Any] = {
        **base_payload,
        "map_type": "structure",
        "kind": "structure",
        "title": f"Structure — {root_title or 'Agent execution'}",
        "settings": {"map_type": "structure", "graph_mode": "execution"},
    }
    structure_payload["tree"] = build_tree_view(structure_payload)

    # ── Assemble variants ─────────────────────────────────────────────────────
    variants: dict[str, dict[str, Any]] = {
        "work_graph": base_payload,
        "context_mindmap": context_payload,
        "structure": structure_payload,
        "evidence": evidence_payload,
    }

    # ── Build reasoning map when requested and answer text is present ─────────
    reasoning_map: dict[str, Any] | None = None
    if include_reasoning_map and answer_text.strip() and source_rows:
        # Map citation [n] index → work-graph source node id for cross-linking
        src_node_id_map: dict[int, str] = {
            si: f"evidence_{si}" for si in range(1, min(len(source_rows), 24) + 1)
        }
        rm = _build_reasoning_map(answer_text=answer_text, source_node_ids=src_node_id_map)
        if rm.get("nodes") or rm.get("edges"):
            reasoning_map = rm

    all_variant_keys: list[str] = ["work_graph", "context_mindmap", "structure", "evidence"]
    available_map_types: list[str] = [k for k in all_variant_keys if k in variants]

    selected_payload = dict(variants.get(map_type_norm, variants["context_mindmap"]))
    selected_payload["variants"] = {
        key: value for key, value in variants.items() if key != selected_payload["map_type"]
    }
    selected_payload["available_map_types"] = available_map_types
    if reasoning_map is not None:
        selected_payload["reasoning_map"] = reasoning_map
    selected_payload.setdefault("settings", {})
    selected_payload["settings"]["map_type"] = selected_payload["map_type"]
    # Metadata hints for the frontend renderer
    selected_payload.setdefault("view_hint", selected_payload["map_type"])
    selected_payload.setdefault("subtitle", compact_text(request_message, max_len=120))
    selected_payload.setdefault(
        "artifact_summary",
        f"{len(action_rows)} action(s), {len(source_rows)} source(s)",
    )
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
    # Derive a document summary from the first chunks to improve reasoning map quality
    _summary_sentences = [
        s.strip()
        for row in documents[:4]
        for s in (str(row.get("text", "") or "")).split(". ")
        if len(s.strip()) > 30
    ]
    document_summary = ". ".join(_summary_sentences[:6]).strip()
    if document_summary and not document_summary.endswith("."):
        document_summary += "."
    # Generate LLM reasoning steps when include_reasoning_map is enabled
    llm_reasoning_steps: list[str] | None = None
    if bool(include_reasoning_map) and document_summary:
        llm_reasoning_steps = _generate_reasoning_steps_llm(
            answer_text=document_summary, question=map_title
        ) or None
    payload = build_knowledge_map(
        question=map_title,
        context=context_preview,
        documents=documents,
        answer_text=document_summary,
        max_depth=clipped_depth,
        include_reasoning_map=bool(include_reasoning_map),
        source_type_hint=source_hint(source_name),
        focus={"source_id": source_id, "source_name": source_name},
        map_type=build_map_type,
        reasoning_steps=llm_reasoning_steps,
    )
    # Ensure available_map_types is always present regardless of path taken
    _all_map_keys = ["work_graph", "context_mindmap", "structure", "evidence"]

    if map_type_norm != "context_mindmap":
        if isinstance(payload, dict) and "available_map_types" not in payload:
            known = set(_all_map_keys)
            present = {payload.get("map_type")} | set(
                (payload.get("variants") or {}).keys()
            )
            payload["available_map_types"] = [k for k in _all_map_keys if k in present & known]
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
    present = {"context_mindmap"} | set((normalized.get("variants") or {}).keys())
    normalized["available_map_types"] = [k for k in _all_map_keys if k in present]
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
