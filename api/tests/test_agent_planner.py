import pytest

from api.schemas import ChatRequest
from api.services.agent import planner as planner_module
from api.services.agent.planner import build_plan


@pytest.fixture(autouse=True)
def _disable_llm_paths(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_PLANNER_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_PLAN_CRITIC_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_QUERY_REWRITE_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_WEB_ROUTING_ENABLED", "0")


def test_direct_website_analysis_prioritizes_inspection_and_report_then_server_delivery() -> None:
    request = ChatRequest(
        message=(
            "here is website https://axongroup.com/ analysis and find what they do "
            "and send the report to ssebowadisan1@gmail.com"
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "marketing.web_research" not in tool_ids
    assert tool_ids == [
        "browser.playwright.inspect",
        "report.generate",
    ]
    assert steps[0].params.get("url") == "https://axongroup.com/"


def test_url_prompt_with_explicit_source_discovery_keeps_web_research(monkeypatch) -> None:
    # Web-research branching is now LLM-planner driven rather than keyword heuristics.
    monkeypatch.setattr(
        planner_module,
        "detect_web_routing_mode",
        lambda **kwargs: {"routing_mode": "online_research", "llm_used": True},
    )

    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        return [
            {
                "tool_id": "browser.playwright.inspect",
                "title": "Inspect site",
                "params": {"url": "https://axongroup.com"},
            },
            {
                "tool_id": "marketing.web_research",
                "title": "Discover supporting sources",
                "params": {"query": "site:axongroup.com operations"},
            },
            {
                "tool_id": "report.generate",
                "title": "Generate report",
                "params": {"summary": request.message},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message=(
            "Use https://axongroup.com and search online sources about competitors, then summarize."
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "marketing.web_research" in tool_ids
    assert "browser.playwright.inspect" in tool_ids
    assert "report.generate" in tool_ids
    web_step = next(step for step in steps if step.tool_id == "marketing.web_research")
    assert web_step.params.get("provider") == "brave_search"
    assert web_step.params.get("allow_provider_fallback") is False


def test_build_plan_uses_llm_steps_when_available(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        return [
            {
                "tool_id": "docs.create",
                "title": "Create working doc",
                "params": {"title": "Company Draft"},
            },
            {
                "tool_id": "report.generate",
                "title": "Generate report",
                "params": {"summary": request.message},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message="Prepare a structured company update for leadership.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert tool_ids == [
        "report.generate",
        "docs.create",
    ]


def test_build_plan_preserves_llm_evidence_metadata(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        return [
            {
                "tool_id": "browser.playwright.inspect",
                "title": "Inspect provided website",
                "params": {"url": "https://example.com"},
                "why_this_step": "Need direct source evidence for required facts.",
                "expected_evidence": ["Headquarters city", "Primary services"],
            }
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message="Inspect https://example.com and summarize.",
        agent_mode="ask",
    )
    steps = build_plan(request)
    inspect_step = next(step for step in steps if step.tool_id == "browser.playwright.inspect")
    assert inspect_step.why_this_step.startswith("Need direct source evidence")
    assert list(inspect_step.expected_evidence) == ["Headquarters city", "Primary services"]


def test_highlight_request_adds_file_highlights_and_docs_capture(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        return [
            {
                "tool_id": "browser.playwright.inspect",
                "title": "Inspect provided website",
                "params": {"url": "https://axongroup.com"},
            },
            {
                "tool_id": "documents.highlight.extract",
                "title": "Extract highlighted terms",
                "params": {},
            },
            {
                "tool_id": "docs.create",
                "title": "Write copied highlights",
                "params": {"title": "Copied Highlights"},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message=(
            "Analyze https://axongroup.com, highlight copied words from files and website in green, "
            "then open docs and write the copied words."
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.playwright.inspect" in tool_ids
    assert "documents.highlight.extract" in tool_ids
    assert "docs.create" in tool_ids

    browser_step = next(step for step in steps if step.tool_id == "browser.playwright.inspect")
    docs_step = next(step for step in steps if step.tool_id == "docs.create")
    highlight_step = next(step for step in steps if step.tool_id == "documents.highlight.extract")

    assert browser_step.params.get("highlight_color") == "yellow"
    assert highlight_step.params.get("highlight_color") == "yellow"
    assert docs_step.params.get("include_copied_highlights") is True


def test_location_request_with_url_keeps_location_web_research(monkeypatch) -> None:
    monkeypatch.setattr(
        planner_module,
        "detect_web_routing_mode",
        lambda **kwargs: {"routing_mode": "online_research", "llm_used": True},
    )

    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        return [
            {
                "tool_id": "browser.playwright.inspect",
                "title": "Inspect provided website",
                "params": {"url": "https://axongroup.com/"},
            },
            {
                "tool_id": "marketing.web_research",
                "title": "Gather external evidence",
                "params": {"query": "Axon Group headquarters address"},
            },
            {
                "tool_id": "report.generate",
                "title": "Generate report",
                "params": {"summary": request.message},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message=(
            "analysis https://axongroup.com/ and send an email to "
            "ssebowadisan1@gmail.com about where they are found"
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.playwright.inspect" in tool_ids
    assert "marketing.web_research" in tool_ids
    assert "report.generate" in tool_ids

    web_step = next(step for step in steps if step.tool_id == "marketing.web_research")
    report_step = next(step for step in steps if step.tool_id == "report.generate")
    query = str(web_step.params.get("query") or "").lower()
    report_summary = str(report_step.params.get("summary") or "").lower()

    assert query == "axon group headquarters address"
    assert report_summary != ""


def test_llm_routing_url_scrape_removes_web_research(monkeypatch) -> None:
    monkeypatch.setattr(
        planner_module,
        "detect_web_routing_mode",
        lambda **kwargs: {"routing_mode": "url_scrape", "llm_used": True},
    )
    monkeypatch.setattr(
        planner_module,
        "plan_with_llm",
        lambda **kwargs: [
            {
                "tool_id": "browser.playwright.inspect",
                "title": "Inspect site",
                "params": {"url": "https://axongroup.com"},
            },
            {
                "tool_id": "marketing.web_research",
                "title": "Search online sources",
                "params": {"query": "axon group overview"},
            },
            {
                "tool_id": "report.generate",
                "title": "Generate report",
                "params": {"summary": "check site"},
            },
        ],
    )
    request = ChatRequest(
        message="Please scrape https://axongroup.com and summarize the page.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]
    assert "browser.playwright.inspect" in tool_ids
    assert "marketing.web_research" not in tool_ids
    browser_step = next(step for step in steps if step.tool_id == "browser.playwright.inspect")
    assert browser_step.params.get("web_provider") == "playwright_browser"


def test_deep_search_url_scrape_keeps_web_research(monkeypatch) -> None:
    monkeypatch.setattr(
        planner_module,
        "detect_web_routing_mode",
        lambda **kwargs: {"routing_mode": "url_scrape", "llm_used": True},
    )
    monkeypatch.setattr(
        planner_module,
        "plan_with_llm",
        lambda **kwargs: [
            {
                "tool_id": "browser.playwright.inspect",
                "title": "Inspect site",
                "params": {"url": "https://axongroup.com"},
            },
            {
                "tool_id": "report.generate",
                "title": "Generate report",
                "params": {"summary": "check site"},
            },
        ],
    )
    request = ChatRequest(
        message="Please deeply research https://axongroup.com and include external corroboration.",
        agent_mode="deep_search",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.playwright.inspect" in tool_ids
    assert "marketing.web_research" in tool_ids
    web_step = next(step for step in steps if step.tool_id == "marketing.web_research")
    assert web_step.params.get("provider") == "brave_search"
    assert web_step.params.get("allow_provider_fallback") is False
    assert web_step.params.get("domain_scope_mode") == "strict"
    assert web_step.params.get("domain_scope") == ["axongroup.com"]


def test_company_agent_with_deep_search_override_keeps_web_research(monkeypatch) -> None:
    monkeypatch.setattr(
        planner_module,
        "detect_web_routing_mode",
        lambda **kwargs: {"routing_mode": "none", "llm_used": False},
    )
    monkeypatch.setattr(
        planner_module,
        "plan_with_llm",
        lambda **kwargs: [
            {
                "tool_id": "report.generate",
                "title": "Create concise executive output",
                "params": {"summary": kwargs["request"].message},
            }
        ],
    )
    request = ChatRequest(
        message="Do deep research on renewable energy trends with citations.",
        agent_mode="company_agent",
        setting_overrides={"__deep_search_enabled": True, "__research_depth_tier": "deep_research"},
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "marketing.web_research" in tool_ids
    assert "report.generate" in tool_ids


def test_deep_search_prunes_delivery_tools_from_llm_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        planner_module,
        "detect_web_routing_mode",
        lambda **kwargs: {"routing_mode": "online_research", "llm_used": True},
    )
    monkeypatch.setattr(
        planner_module,
        "plan_with_llm",
        lambda **kwargs: [
            {
                "tool_id": "marketing.web_research",
                "title": "Search online sources",
                "params": {"query": "machine learning"},
            },
            {
                "tool_id": "gmail.send",
                "title": "Send report",
                "params": {"to": "user@example.com"},
            },
            {
                "tool_id": "report.generate",
                "title": "Generate report",
                "params": {"summary": "machine learning"},
            },
        ],
    )
    request = ChatRequest(
        message="Deep research machine learning and send it to user@example.com",
        agent_mode="deep_search",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]
    assert "marketing.web_research" in tool_ids
    assert "report.generate" in tool_ids
    assert "gmail.send" not in tool_ids


def test_contact_form_request_adds_contact_form_send_step(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    monkeypatch.setattr(planner_module, "enrich_task_intelligence", lambda **kwargs: {
        "objective": "Submit a contact form message.",
        "target_url": "https://axongroup.com/contact",
        "requires_delivery": False,
        "requires_web_inspection": True,
        "requires_contact_form_submission": True,
        "requested_report": False,
        "intent_tags": ["contact_form_submission"],
    })
    request = ChatRequest(
        message=(
            "Go to https://axongroup.com/contact and fill the contact form with a business inquiry message."
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.contact_form.send" in tool_ids
    contact_step = next(step for step in steps if step.tool_id == "browser.contact_form.send")
    assert contact_step.params.get("url") == "https://axongroup.com/contact"
    assert "inquiry" in str(contact_step.params.get("subject") or "").lower()


def test_build_plan_uses_llm_intent_semantic_fallback_when_llm_plan_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    monkeypatch.setattr(
        planner_module,
        "enrich_task_intelligence",
        lambda **kwargs: {
            "objective": "Determine where Axon Group is located and share findings.",
            "target_url": "https://axongroup.com/",
            "delivery_email": "ssebowadisan1@gmail.com",
            "requires_delivery": True,
            "requires_web_inspection": True,
            "requested_report": True,
            "intent_tags": ["docs_write"],
        },
    )
    request = ChatRequest(
        message="yo check this company out and mail where they are based to ssebowadisan1@gmail.com",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.playwright.inspect" in tool_ids
    assert "report.generate" in tool_ids
    assert "docs.create" in tool_ids
    assert "gmail.send" not in tool_ids


def test_semantic_fallback_can_request_contact_form_submission(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    monkeypatch.setattr(
        planner_module,
        "enrich_task_intelligence",
        lambda **kwargs: {
            "objective": "Reach out via the website contact form.",
            "target_url": "https://axongroup.com/contact",
            "requires_delivery": False,
            "requires_web_inspection": True,
            "requires_contact_form_submission": True,
            "requested_report": False,
            "preferred_format": "",
        },
    )
    request = ChatRequest(
        message="Contact them through their website form.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.contact_form.send" in tool_ids
    contact_step = next(step for step in steps if step.tool_id == "browser.contact_form.send")
    assert contact_step.params.get("url") == "https://axongroup.com/contact"


def test_llm_plan_can_select_business_route_plan(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        _ = request
        assert "business.route_plan" in allowed_tool_ids
        return [
            {
                "tool_id": "business.route_plan",
                "title": "Create business route plan",
                "params": {
                    "origin": "Kampala office",
                    "destinations": ["Entebbe Airport", "Jinja"],
                },
            }
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message="Please create a route plan from Kampala office to Entebbe Airport and Jinja for today visits.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "business.route_plan" in tool_ids
    route_step = next(step for step in steps if step.tool_id == "business.route_plan")
    assert str(route_step.params.get("origin") or "").lower().startswith("kampala office")
    destinations = route_step.params.get("destinations")
    assert isinstance(destinations, list)
    assert len(destinations) >= 1


def test_llm_plan_can_select_business_ga4_workflow(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        _ = request
        assert "business.ga4_kpi_sheet_report" in allowed_tool_ids
        return [
            {
                "tool_id": "business.ga4_kpi_sheet_report",
                "title": "Generate GA4 KPI report in Google Sheets",
                "params": {"sheet_range": "Tracker!A1"},
            }
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message="Create a weekly GA4 KPI report and put it in Google Sheets.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "business.ga4_kpi_sheet_report" in tool_ids


def test_ga4_request_in_deep_mode_does_not_auto_insert_web_research(monkeypatch) -> None:
    monkeypatch.setattr(
        planner_module,
        "plan_with_llm",
        lambda **kwargs: [
            {
                "tool_id": "report.generate",
                "title": "Generate report",
                "params": {"summary": kwargs["request"].message},
            }
        ],
    )
    request = ChatRequest(
        message="Create a detailed Google Analytics GA4 report for property 479179141.",
        agent_mode="deep_search",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "analytics.ga4.full_report" in tool_ids
    assert "marketing.web_research" not in tool_ids
    report_step = next(step for step in steps if step.tool_id == "report.generate")
    assert report_step.params.get("sources") == []


def test_ga4_sheet_request_enforces_ga_steps_when_llm_plan_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    monkeypatch.setattr(
        planner_module,
        "enrich_task_intelligence",
        lambda **kwargs: {
            "objective": "Generate a GA4 KPI report and write it to sheets.",
            "requires_web_inspection": False,
            "requested_report": True,
            "wants_sheets_output": True,
            "intent_tags": ["sheets_update"],
        },
    )
    request = ChatRequest(
        message="Generate a Google Analytics GA4 KPI report and update the tracker sheet.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "analytics.ga4.full_report" in tool_ids
    assert "business.ga4_kpi_sheet_report" in tool_ids
    assert "marketing.web_research" not in tool_ids
    report_step = next(step for step in steps if step.tool_id == "report.generate")
    assert report_step.params.get("sources") == []


def test_llm_plan_can_select_business_cloud_incident_workflow(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        _ = request
        assert "business.cloud_incident_digest_email" in allowed_tool_ids
        return [
            {
                "tool_id": "business.cloud_incident_digest_email",
                "title": "Send cloud incident digest email",
                "params": {"to": "ops@example.com", "send": True},
            }
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message="Send a cloud incident digest email to ops@example.com from cloud logging.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "business.cloud_incident_digest_email" in tool_ids
    digest_step = next(step for step in steps if step.tool_id == "business.cloud_incident_digest_email")
    assert digest_step.params.get("to") == "ops@example.com"


def test_llm_plan_can_select_business_invoice_workflow(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        _ = request
        assert "business.invoice_workflow" in allowed_tool_ids
        return [
            {
                "tool_id": "business.invoice_workflow",
                "title": "Run invoice workflow",
                "params": {
                    "invoice_number": "INV-2026-001",
                    "to": "billing@example.com",
                    "send": True,
                },
            }
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message="Create and send invoice INV-2026-001 to client for USD 1200 and email it to billing@example.com.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "business.invoice_workflow" in tool_ids
    invoice_step = next(step for step in steps if step.tool_id == "business.invoice_workflow")
    assert invoice_step.params.get("invoice_number") == "INV-2026-001"
    assert invoice_step.params.get("to") == "billing@example.com"
    assert invoice_step.params.get("send") is True


def test_llm_plan_can_select_business_meeting_scheduler(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        _ = request
        assert "business.meeting_scheduler" in allowed_tool_ids
        return [
            {
                "tool_id": "business.meeting_scheduler",
                "title": "Schedule meeting workflow",
                "params": {"attendees": ["opslead@example.com"]},
            }
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message="Schedule a meeting with opslead@example.com to review Q2 rollout.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "business.meeting_scheduler" in tool_ids
    meeting_step = next(step for step in steps if step.tool_id == "business.meeting_scheduler")
    attendees = meeting_step.params.get("attendees")
    assert isinstance(attendees, list)
    assert "opslead@example.com" in attendees


def test_llm_plan_can_select_business_proposal_workflow(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        _ = request
        assert "business.proposal_workflow" in allowed_tool_ids
        return [
            {
                "tool_id": "business.proposal_workflow",
                "title": "Create proposal workflow",
                "params": {"to": "ceo@example.com"},
            }
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message="Create an RFP proposal draft and send to ceo@example.com for review.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "business.proposal_workflow" in tool_ids
    proposal_step = next(step for step in steps if step.tool_id == "business.proposal_workflow")
    assert proposal_step.params.get("to") == "ceo@example.com"


def test_data_science_plan_can_be_llm_driven_without_keyword_fallback(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        _ = request
        assert "data.science.profile" in allowed_tool_ids
        assert "data.science.ml.train" in allowed_tool_ids
        assert "data.science.visualize" in allowed_tool_ids
        return [
            {
                "tool_id": "data.science.profile",
                "title": "Profile dataset",
                "params": {},
            },
            {
                "tool_id": "data.science.ml.train",
                "title": "Train ML model",
                "params": {"target": "churn"},
            },
            {
                "tool_id": "data.science.visualize",
                "title": "Visualize results",
                "params": {"chart_type": "histogram"},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message=(
            "Analyze this dataset, train a machine learning model to predict churn "
            "target: churn, and show a chart."
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "data.science.profile" in tool_ids
    assert "data.science.ml.train" in tool_ids
    assert "data.science.visualize" in tool_ids
    ml_step = next(step for step in steps if step.tool_id == "data.science.ml.train")
    assert ml_step.params.get("target") == "churn"


def test_build_plan_scopes_allowed_tools_when_preferred_tools_are_provided(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("MAIA_AGENT_LLM_WIDE_TOOLSET_ENABLED", "0")

    def _fake_plan_with_llm(*, request, allowed_tool_ids, preferred_tool_ids):
        _ = request
        captured["allowed_tool_ids"] = set(allowed_tool_ids)
        captured["preferred_tool_ids"] = set(preferred_tool_ids)
        return []

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    monkeypatch.setattr(planner_module, "optimize_plan_rows", lambda **kwargs: kwargs["rows"])
    request = ChatRequest(
        message="Use Google Sheets API to update KPI rows.",
        agent_mode="company_agent",
    )
    _ = build_plan(request, preferred_tool_ids={"google.api.google_sheets"})
    allowed = captured.get("allowed_tool_ids")
    assert isinstance(allowed, set)
    assert "google.api.google_sheets" in allowed
    assert "workspace.sheets.track_step" not in allowed
    assert "workspace.docs.research_notes" not in allowed
    assert "report.generate" in allowed
    assert "invoice.send" not in allowed


def test_simple_definition_request_avoids_web_research_when_routing_is_none(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    request = ChatRequest(
        message="what is machine learning",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "marketing.web_research" not in tool_ids
    assert "report.generate" in tool_ids


def test_explicit_online_search_request_keeps_web_research_step(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    monkeypatch.setattr(
        planner_module,
        "detect_web_routing_mode",
        lambda **kwargs: {"routing_mode": "online_research", "llm_used": True},
    )
    request = ChatRequest(
        message="search online for the latest machine learning trends and summarize",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "marketing.web_research" in tool_ids


def test_attachment_scoped_company_agent_prunes_web_steps(monkeypatch) -> None:
    monkeypatch.setattr(
        planner_module,
        "detect_web_routing_mode",
        lambda **kwargs: {"routing_mode": "online_research", "llm_used": True},
    )
    monkeypatch.setattr(
        planner_module,
        "plan_with_llm",
        lambda **kwargs: [
            {
                "tool_id": "marketing.web_research",
                "title": "Search online sources",
                "params": {"query": "attached pdf summary"},
            },
            {
                "tool_id": "documents.highlight.extract",
                "title": "Highlight words in selected files",
                "params": {},
            },
            {
                "tool_id": "report.generate",
                "title": "Create concise executive output",
                "params": {"summary": kwargs["request"].message},
            },
        ],
    )
    request = ChatRequest(
        message="Read the attached PDF and summarize it with citations.",
        agent_mode="company_agent",
        attachments=[{"name": "notes.pdf", "file_id": "file-123"}],
        index_selection={"1": {"mode": "select", "file_ids": ["file-123"]}},
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "documents.highlight.extract" in tool_ids
    assert "report.generate" in tool_ids
    assert "marketing.web_research" not in tool_ids
    assert "browser.playwright.inspect" not in tool_ids


def test_attachment_scoped_deep_search_keeps_web_steps(monkeypatch) -> None:
    monkeypatch.setattr(
        planner_module,
        "detect_web_routing_mode",
        lambda **kwargs: {"routing_mode": "online_research", "llm_used": True},
    )
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    request = ChatRequest(
        message="Deeply research this attached PDF and compare with online trends.",
        agent_mode="deep_search",
        attachments=[{"name": "notes.pdf", "file_id": "file-123"}],
        index_selection={"1": {"mode": "select", "file_ids": ["file-123"]}},
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "marketing.web_research" in tool_ids
    assert "report.generate" in tool_ids


def test_generic_prompt_does_not_force_pdf_highlight_step(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    request = ChatRequest(
        message="what is machine learning",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "documents.highlight.extract" not in tool_ids


def test_build_browser_followup_steps_prioritizes_pdf_sources() -> None:
    followups = planner_module.build_browser_followup_steps(
        {
            "items": [
                {"label": "Website article", "url": "https://example.com/article"},
                {"label": "Research PDF", "url": "https://example.com/research-paper.pdf"},
            ]
        },
        max_urls=1,
    )
    assert len(followups) == 1
    assert followups[0].tool_id == "browser.playwright.inspect"
    assert str(followups[0].params.get("url") or "").endswith(".pdf")
    assert followups[0].params.get("follow_same_domain_links") is False


def test_attachment_intent_enables_doc_export_and_gmail_attachment(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        _ = (request, allowed_tool_ids)
        return [
            {
                "tool_id": "workspace.docs.fill_template",
                "title": "Write report in Google Docs",
                "params": {"title": "Market Report"},
            },
            {
                "tool_id": "gmail.send",
                "title": "Send report email",
                "params": {},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    monkeypatch.setattr(
        planner_module,
        "intent_signals",
        lambda request: {
            "url": "",
            "recipient_email": "ops@example.com",
            "wants_attachment_delivery": True,
            "wants_file_scope": False,
            "highlight_color": "yellow",
        },
    )
    request = ChatRequest(
        message="Research AI agents, write report, download pdf and send attached to ops@example.com",
        agent_mode="ask",
    )
    steps = build_plan(request)

    docs_step = next(step for step in steps if step.tool_id == "workspace.docs.fill_template")
    gmail_step = next(step for step in steps if step.tool_id == "gmail.send")

    assert docs_step.params.get("export_pdf") is True
    assert gmail_step.params.get("attach_latest_report_pdf") is True
    assert gmail_step.params.get("to") == "ops@example.com"


def test_no_attachment_intent_does_not_force_doc_export_or_email_attachment(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        _ = (request, allowed_tool_ids)
        return [
            {
                "tool_id": "workspace.docs.fill_template",
                "title": "Write report in Google Docs",
                "params": {"title": "Market Report"},
            },
            {
                "tool_id": "gmail.send",
                "title": "Send report email",
                "params": {},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    monkeypatch.setattr(
        planner_module,
        "intent_signals",
        lambda request: {
            "url": "",
            "recipient_email": "ops@example.com",
            "wants_attachment_delivery": False,
            "wants_file_scope": False,
            "highlight_color": "yellow",
        },
    )
    request = ChatRequest(
        message="Research AI agents and send the summary to ops@example.com",
        agent_mode="ask",
    )
    steps = build_plan(request)

    docs_step = next(step for step in steps if step.tool_id == "workspace.docs.fill_template")
    gmail_step = next(step for step in steps if step.tool_id == "gmail.send")

    assert "export_pdf" not in docs_step.params
    assert "attach_latest_report_pdf" not in gmail_step.params
