import sys
import types

try:
    from api.services import mindmap_service
except ModuleNotFoundError:
    ktem_module = types.ModuleType("ktem")
    db_module = types.ModuleType("ktem.db")
    models_module = types.ModuleType("ktem.db.models")
    models_module.engine = None
    db_module.models = models_module
    ktem_module.db = db_module
    sys.modules.setdefault("ktem", ktem_module)
    sys.modules.setdefault("ktem.db", db_module)
    sys.modules.setdefault("ktem.db.models", models_module)
    maia_module = types.ModuleType("maia")
    maia_mindmap_module = types.ModuleType("maia.mindmap")
    maia_indexer_module = types.ModuleType("maia.mindmap.indexer")

    def _stub_build_knowledge_map(**kwargs):
        map_type = str(kwargs.get("map_type", "structure") or "structure")
        return {
            "version": 1,
            "map_type": map_type,
            "kind": "graph",
            "title": str(kwargs.get("question") or "Map"),
            "root_id": "root",
            "nodes": [{"id": "root", "title": str(kwargs.get("question") or "Map")}],
            "edges": [],
            "settings": {"map_type": map_type},
            "variants": {},
        }

    maia_indexer_module.build_knowledge_map = _stub_build_knowledge_map
    maia_mindmap_module.indexer = maia_indexer_module
    maia_module.mindmap = maia_mindmap_module
    sys.modules.setdefault("maia", maia_module)
    sys.modules.setdefault("maia.mindmap", maia_mindmap_module)
    sys.modules.setdefault("maia.mindmap.indexer", maia_indexer_module)
    from api.services import mindmap_service


def test_normalize_map_type_supports_work_graph_aliases() -> None:
    assert mindmap_service._normalize_map_type("work_graph") == "work_graph"
    assert mindmap_service._normalize_map_type("work graph") == "work_graph"
    assert mindmap_service._normalize_map_type("execution graph") == "work_graph"
    assert mindmap_service._normalize_map_type("context mindmap") == "context_mindmap"
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
    assert {"structure", "evidence", "context_mindmap"}.issubset(set(payload["variants"].keys()))
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
    assert payload["graph"]["schema"] == "context_mindmap.v1"
    variants = payload.get("variants", {})
    assert isinstance(variants, dict)
    assert "work_graph" in variants


def test_build_agent_work_graph_supports_context_mindmap_variant() -> None:
    payload = mindmap_service.build_agent_work_graph(
        request_message="Research and summarize",
        actions_taken=[
            {
                "tool_id": "marketing.web_research",
                "action_class": "read",
                "status": "success",
                "summary": "Collect web evidence",
            }
        ],
        sources_used=[
            {
                "source_type": "web",
                "label": "Axon Group | Products",
                "url": "https://axongroup.com/products-and-solutions",
            }
        ],
        map_type="context_mindmap",
    )

    assert payload["map_type"] == "context_mindmap"
    assert payload["kind"] == "context_mindmap"
    assert payload["graph"]["schema"] == "context_mindmap.v1"
    node_types = {str(item.get("node_type", "")) for item in payload.get("nodes", []) if isinstance(item, dict)}
    assert "source" in node_types
