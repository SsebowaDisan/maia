from api.services import mindmap_service


def test_normalize_map_type_supports_work_graph_aliases() -> None:
    assert mindmap_service._normalize_map_type("work_graph") == "work_graph"
    assert mindmap_service._normalize_map_type("work graph") == "work_graph"
    assert mindmap_service._normalize_map_type("execution graph") == "work_graph"
    assert mindmap_service._normalize_map_type("evidence") == "evidence"
    assert mindmap_service._normalize_map_type("unknown") == "structure"


def test_build_agent_work_graph_emits_execution_nodes_and_variants() -> None:
    payload = mindmap_service.build_agent_work_graph(
        request_message="Analyze the target site and send a verified report",
        actions_taken=[
            {
                "tool_id": "browser.playwright.inspect",
                "action_class": "read",
                "status": "success",
                "summary": "Inspect site navigation and key pages",
                "started_at": "2026-03-07T11:00:00Z",
                "ended_at": "2026-03-07T11:00:03Z",
            },
            {
                "tool_id": "email.send",
                "action_class": "execute",
                "status": "failed",
                "summary": "Send the final report",
                "started_at": "2026-03-07T11:00:04Z",
                "ended_at": "2026-03-07T11:00:05Z",
            },
        ],
        sources_used=[
            {
                "source_type": "web",
                "label": "Axon Group | About",
                "url": "https://axongroup.com/about-axon",
            }
        ],
        map_type="work_graph",
        run_id="run_123",
    )

    assert payload["map_type"] == "work_graph"
    assert payload["kind"] == "work_graph"
    assert payload["root_id"] == "task_run_123"
    assert isinstance(payload.get("nodes"), list) and len(payload["nodes"]) >= 4
    assert isinstance(payload.get("edges"), list) and len(payload["edges"]) >= 3
    assert isinstance(payload.get("variants"), dict)
    assert {"structure", "evidence"}.issubset(set(payload["variants"].keys()))
    assert payload["graph"]["schema"] == "work_graph.v1"


def test_build_agent_work_graph_selects_variant_map_type() -> None:
    payload = mindmap_service.build_agent_work_graph(
        request_message="Summarize findings",
        actions_taken=[
            {
                "tool_id": "report.generate",
                "action_class": "draft",
                "status": "success",
                "summary": "Draft report",
            }
        ],
        sources_used=[],
        map_type="evidence",
    )

    assert payload["map_type"] == "evidence"
    assert payload["kind"] == "graph"
    variants = payload.get("variants", {})
    assert isinstance(variants, dict)
    assert "work_graph" in variants
