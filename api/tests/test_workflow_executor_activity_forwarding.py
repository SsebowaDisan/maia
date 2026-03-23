from __future__ import annotations

import sys
from types import SimpleNamespace

from api.services.agents import workflow_executor as module
from api.schemas.workflow_definition import WorkflowStep


def test_run_agent_step_unwraps_activity_stream_events(monkeypatch) -> None:
    fake_record = SimpleNamespace(agent_id="researcher")
    fake_schema = SimpleNamespace(
        system_prompt="",
        tools=[],
        max_tool_calls_per_run=None,
    )

    def _fake_get_agent(tenant_id: str, agent_id: str):
        return fake_record

    def _fake_load_schema(record):
        return fake_schema

    observed_kwargs: dict[str, object] = {}
    persisted: list[object] = []

    def _fake_run_agent_task(*args, **kwargs):
        observed_kwargs.update(kwargs)
        yield {
            "type": "activity",
            "event": {
                "event_type": "browser_navigate",
                "event_id": "evt_nav",
                "run_id": "child_run_1",
                "title": "Navigate",
                "detail": "Opening source page",
                "timestamp": "2026-01-01T00:00:00Z",
                "data": {"url": "https://example.com", "run_id": "child_run_1"},
                "metadata": {},
            },
        }
        yield {"type": "chat_delta", "delta": "hello", "text": "hello"}
        yield {"event_type": "budget_exceeded", "detail": "limit reached"}

    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.definition_store",
        SimpleNamespace(get_agent=_fake_get_agent, load_schema=_fake_load_schema),
    )
    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.runner",
        SimpleNamespace(run_agent_task=_fake_run_agent_task),
    )
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)
    monkeypatch.setattr(
        "api.services.agent.activity.get_activity_store",
        lambda: SimpleNamespace(append=lambda event: persisted.append(event)),
    )

    captured: list[dict] = []
    result = module._run_agent_step(
        "researcher",
        {"task": "research topic"},
        "tenant_1",
        run_id="parent_run_1",
        on_event=lambda event: captured.append(dict(event)),
    )

    assert result == "hello"
    event_types = [str(event.get("event_type") or "").strip().lower() for event in captured]
    assert "browser_navigate" in event_types
    assert "budget_exceeded" in event_types
    assert "chat_delta" not in event_types
    assert observed_kwargs["run_id"] == "parent_run_1"
    browser_event = next(event for event in captured if str(event.get("event_type")) == "browser_navigate")
    assert browser_event["run_id"] == "parent_run_1"
    assert browser_event["data"]["run_id"] == "parent_run_1"
    assert browser_event["source_run_id"] == "child_run_1"
    assert persisted
    persisted_event = persisted[0]
    assert persisted_event.run_id == "parent_run_1"
    assert persisted_event.event_type == "browser_navigate"


def test_dispatch_step_sends_cited_delivery_draft_directly(monkeypatch) -> None:
    sent_payload: dict[str, str] = {}
    persisted: list[object] = []

    monkeypatch.setattr(
        module,
        "send_report_email",
        lambda **kwargs: sent_payload.update(
            {
                "to_email": str(kwargs.get("to_email") or ""),
                "subject": str(kwargs.get("subject") or ""),
                "body_text": str(kwargs.get("body_text") or ""),
            }
        )
        or {"id": "msg_123"},
    )
    monkeypatch.setattr(
        "api.services.agent.activity.get_activity_store",
        lambda: SimpleNamespace(append=lambda event: persisted.append(event)),
    )

    events: list[dict[str, object]] = []
    step = WorkflowStep(
        step_id="step_3",
        step_type="agent",
        agent_id="delivery-specialist",
        description="Send the approved cited email draft to ssebowadisan1@gmail.com without changing its substance.",
        output_key="delivery_output",
        step_config={"tool_ids": ["mailer.report_send"]},
    )
    draft = (
        "Subject: Machine Learning Research Brief\n\n"
        "## Executive Summary\n"
        "Machine learning helps systems learn patterns from data [1].\n\n"
        "## Evidence Citations\n"
        "- [1] [IBM Machine Learning](https://www.ibm.com/think/topics/machine-learning)"
    )

    result = module._dispatch_step(
        step,
        {"email_specialist": draft, "recipient": "ssebowadisan1@gmail.com"},
        "tenant_1",
        "run_delivery_1",
        on_event=lambda event: events.append(dict(event)),
    )

    assert result.startswith("To: ssebowadisan1@gmail.com")
    assert sent_payload["to_email"] == "ssebowadisan1@gmail.com"
    assert sent_payload["subject"] == "Machine Learning Research Brief"
    assert "## Evidence Citations" in sent_payload["body_text"]
    event_types = [str(event.get("event_type") or "") for event in events]
    assert "email_ready_to_send" in event_types
    assert "email_sent" in event_types
    assert persisted


def test_run_agent_step_scopes_task_to_step_objective(monkeypatch) -> None:
    fake_record = SimpleNamespace(agent_id="writer")
    fake_schema = SimpleNamespace(
        system_prompt="",
        tools=[],
        max_tool_calls_per_run=None,
    )

    def _fake_get_agent(tenant_id: str, agent_id: str):
        return fake_record

    def _fake_load_schema(record):
        return fake_schema

    observed: dict[str, object] = {}

    def _fake_run_agent_task(task, *args, **kwargs):
        observed["task"] = task
        yield {"type": "chat_delta", "delta": "done", "text": "done"}

    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.definition_store",
        SimpleNamespace(get_agent=_fake_get_agent, load_schema=_fake_load_schema),
    )
    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.runner",
        SimpleNamespace(run_agent_task=_fake_run_agent_task),
    )
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)

    step = WorkflowStep(
        step_id="step_2",
        step_type="agent",
        agent_id="writer",
        description="Write a cited executive email summary from the verified findings.",
        output_key="writer_output",
        step_config={},
    )
    result = module._run_agent_step(
        "writer",
        {
            "message": "make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
            "research_output": "Machine learning includes supervised, unsupervised, and reinforcement learning.",
        },
        "tenant_1",
        run_id="parent_run_2",
        on_event=lambda event: None,
        step=step,
    )

    assert result == "done"
    task = str(observed.get("task") or "")
    assert "Current stage objective" in task
    assert "Write a cited executive email summary from the verified findings." in task
    assert "Stage completion rule" in task
    assert "Available context and previous outputs" in task
    assert "research_output" in task
    assert "Original user request for reference only" not in task
    assert "write an email about the research to ssebowadisan1@gmail.com" not in task


def test_run_agent_step_passes_stage_topic_overrides_to_runner(monkeypatch) -> None:
    fake_record = SimpleNamespace(agent_id="researcher")
    fake_schema = SimpleNamespace(system_prompt="", tools=["marketing.web_research"], max_tool_calls_per_run=None)

    def _fake_get_agent(tenant_id: str, agent_id: str):
        return fake_record

    def _fake_load_schema(record):
        return fake_schema

    observed_kwargs: dict[str, object] = {}

    def _fake_run_agent_task(task, *args, **kwargs):
        observed_kwargs.update(kwargs)
        yield {"type": "chat_delta", "delta": "done", "text": "done"}

    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.definition_store",
        SimpleNamespace(get_agent=_fake_get_agent, load_schema=_fake_load_schema),
    )
    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.runner",
        SimpleNamespace(run_agent_task=_fake_run_agent_task),
    )
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)

    step = WorkflowStep(
        step_id="step_1",
        step_type="agent",
        agent_id="researcher",
        description="Research machine learning from authoritative sources.",
        output_key="research_output",
        step_config={"tool_ids": ["marketing.web_research"]},
    )
    result = module._run_agent_step(
        "researcher",
        {"query": "machine learning", "message": "unused broad prompt"},
        "tenant_1",
        run_id="run_seeded_1",
        on_event=lambda event: None,
        step=step,
    )

    assert result == "done"
    assert observed_kwargs["settings_overrides"] == {
        "__workflow_stage_primary_topic": "machine learning",
        "__research_search_terms": ["machine learning"],
    }


def test_run_step_with_retry_skips_brain_review_after_direct_delivery(monkeypatch) -> None:
    step = WorkflowStep(
        step_id="step_3",
        step_type="agent",
        agent_id="delivery-specialist",
        description="Send the cited email draft produced by the previous step to ssebowadisan1@gmail.com without changing its substance.",
        output_key="delivery_output",
        step_config={"tool_ids": ["mailer.report_send"]},
    )

    monkeypatch.setattr(module, "_validate_stage_contract", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_run_quality_gate", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_emit_step_kickoff_chat", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_dispatch_step", lambda *args, **kwargs: "To: ssebowadisan1@gmail.com\nSubject: Research Brief\n\nBody [1]")

    def _fail_review(*args, **kwargs):
        raise AssertionError("brain review should be skipped after direct delivery")

    monkeypatch.setattr(module, "_run_brain_review", _fail_review)

    result = module._run_step_with_retry(
        step,
        {"writer": "Subject: Research Brief\n\nBody [1]", "recipient": "ssebowadisan1@gmail.com"},
        "tenant_1",
        "wf_1",
        "run_delivery_skip_review",
        on_event=lambda event: None,
        step_timeout_s=420,
    )

    assert result.startswith("To: ssebowadisan1@gmail.com")


def test_draft_only_step_is_never_treated_as_direct_delivery() -> None:
    step = WorkflowStep(
        step_id="step_2",
        step_type="agent",
        agent_id="email-specialist",
        description=(
            "Compose a polished, citation-rich email draft about machine learning for "
            "ssebowadisan1@gmail.com. This stage drafts only; do not dispatch the email."
        ),
        output_key="output_step_2",
        step_config={"tool_ids": ["report.generate", "gmail.send", "mailer.report_send"]},
    )

    assert module._is_direct_delivery_candidate(
        step,
        {
            "research_specialist": "Subject: Brief\n\nBody [1]",
            "recipient": "ssebowadisan1@gmail.com",
        },
    ) is False


def test_dispatch_step_does_not_run_direct_delivery_for_draft_only_stage(monkeypatch) -> None:
    step = WorkflowStep(
        step_id="step_2",
        step_type="agent",
        agent_id="email-specialist",
        description=(
            "Compose a polished, citation-rich email draft about machine learning for "
            "ssebowadisan1@gmail.com. This stage drafts only; do not dispatch the email."
        ),
        output_key="output_step_2",
        step_config={"tool_ids": ["report.generate", "gmail.send", "mailer.report_send"]},
    )

    called = {"send": False, "grounded": False, "agent": False}

    def _fake_direct_delivery_step(**kwargs):
        called["send"] = True
        return "should not send"

    def _fake_run_agent_step(*args, **kwargs):
        called["agent"] = True
        return "draft output"

    def _fake_grounded_email_draft_step(**kwargs):
        called["grounded"] = True
        return "grounded draft output"

    monkeypatch.setitem(
        sys.modules,
        "api.services.agent.approval_workflows",
        SimpleNamespace(
            get_approval_service=lambda: SimpleNamespace(
                requires_approval=lambda *args, **kwargs: False
            )
        ),
    )
    monkeypatch.setattr(module, "_run_direct_delivery_step", _fake_direct_delivery_step)
    monkeypatch.setattr(module, "_run_grounded_email_draft_step", _fake_grounded_email_draft_step)
    monkeypatch.setattr(module, "_run_agent_step", _fake_run_agent_step)

    result = module._dispatch_step(
        step,
        {
            "research_specialist": "## Findings\nBody [1]\n\n## Evidence Citations\n- [1] [Source](https://example.com)",
            "recipient": "ssebowadisan1@gmail.com",
        },
        "tenant_1",
        "run_draft_only_dispatch",
        on_event=lambda event: None,
    )

    assert result == "grounded draft output"
    assert called["send"] is False
    assert called["grounded"] is True
    assert called["agent"] is False


def test_run_step_with_retry_skips_brain_review_after_grounded_email_draft(monkeypatch) -> None:
    step = WorkflowStep(
        step_id="step_2",
        step_type="agent",
        agent_id="email-specialist",
        description=(
            "Compose a polished, citation-rich email draft about machine learning for "
            "ssebowadisan1@gmail.com. This stage drafts only; do not dispatch the email."
        ),
        output_key="writer_output",
        step_config={"tool_ids": ["report.generate", "gmail.draft", "mailer.report_send"]},
    )

    monkeypatch.setattr(module, "_validate_stage_contract", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_run_quality_gate", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_emit_step_kickoff_chat", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_dispatch_step", lambda *args, **kwargs: "Subject: Research Brief\n\nHi,\n\nBody [1]\n\n## Evidence Citations\n- [1] [Source](https://example.com)")

    def _fail_review(*args, **kwargs):
        raise AssertionError("brain review should be skipped after grounded email draft")

    monkeypatch.setattr(module, "_run_brain_review", _fail_review)

    result = module._run_step_with_retry(
        step,
        {"research_specialist": "## Findings\nResult [1]\n\n## Evidence Citations\n- [1] [Source](https://example.com)", "recipient": "ssebowadisan1@gmail.com"},
        "tenant_1",
        "wf_1",
        "run_grounded_skip_review",
        on_event=lambda event: None,
        step_timeout_s=420,
    )

    assert result.startswith("Subject: Research Brief")


def test_normalize_grounded_email_result_rewrites_instruction_echo_subject() -> None:
    citation_section = "## Evidence Citations\n- [1] [Source](https://example.com)"
    result = module._normalize_grounded_email_result(
        result=(
            "Subject: Compose a polished, citation-rich email draft about machine learning for ssebowadisan1@gmail.com\n\n"
            "Hi ssebowadisan1@gmail.com,\n\nBody [1]"
        ),
        required_subject="Machine Learning Research Brief",
        citation_section=citation_section,
    )

    assert result.startswith("Subject: Machine Learning Research Brief")
    assert "Compose a polished, citation-rich email draft" not in result
    assert "## Evidence Citations" in result


def test_is_valid_grounded_email_draft_rejects_internal_execution_summary() -> None:
    citation_section = "## Evidence Citations\n- [1] [Source](https://example.com)"

    assert module._is_valid_grounded_email_draft(
        "Subject: Machine Learning Research Brief\n\n"
        "## Executive Summary\n"
        "- Findings are grounded in executed tools and verified source evidence.\n\n"
        "## Evidence Citations\n"
        "- [1] [Source](https://example.com)",
        citation_section=citation_section,
    ) is False


def test_choose_delivery_artifact_prefers_mapped_draft_over_handoff_context() -> None:
    step = WorkflowStep(
        step_id="step_3",
        step_type="agent",
        agent_id="delivery-specialist",
        description="Send the cited email draft produced by the previous step to ssebowadisan1@gmail.com without changing its substance.",
        output_key="output_step_3",
        input_mapping={"Email Specialist": "output_step_2", "recipient": "literal:ssebowadisan1@gmail.com"},
        step_config={"tool_ids": ["mailer.report_send"]},
    )
    email_draft = (
        "Subject: Machine Learning Research Brief\n\n"
        "Hi ssebowadisan1@gmail.com,\n\n"
        "Machine learning is increasingly central to modern software and science [1].\n\n"
        "Best regards,\n"
        "Maia\n\n"
        "## Evidence Citations\n"
        "- [1] [Source](https://example.com)"
    )
    handoff_context = (
        "The email-specialist agent has completed their work and handed off to you.\n\n"
        "Summary of their findings:\n"
        "Subject: Broken summary\n\n"
        "Your task: Send the cited email draft produced by the previous step."
    )

    selected = module._choose_delivery_artifact(
        {
            "Email Specialist": email_draft,
            "__handoff_context": handoff_context,
            "recipient": "ssebowadisan1@gmail.com",
        },
        step=step,
    )

    assert selected == email_draft


def test_dispatch_step_direct_delivery_ignores_handoff_summary_text(monkeypatch) -> None:
    sent_payload: dict[str, str] = {}
    monkeypatch.setattr(
        module,
        "send_report_email",
        lambda **kwargs: sent_payload.update(
            {
                "to_email": str(kwargs.get("to_email") or ""),
                "subject": str(kwargs.get("subject") or ""),
                "body_text": str(kwargs.get("body_text") or ""),
            }
        )
        or {"id": "msg_456"},
    )
    step = WorkflowStep(
        step_id="step_3",
        step_type="agent",
        agent_id="delivery-specialist",
        description="Send the cited email draft produced by the previous step to ssebowadisan1@gmail.com without changing its substance.",
        output_key="output_step_3",
        input_mapping={"Email Specialist": "output_step_2", "recipient": "literal:ssebowadisan1@gmail.com"},
        step_config={"tool_ids": ["mailer.report_send"]},
    )
    email_draft = (
        "Subject: Machine Learning Research Brief\n\n"
        "Hi ssebowadisan1@gmail.com,\n\n"
        "Machine learning is increasingly central to modern software and science [1].\n\n"
        "Best regards,\n"
        "Maia\n\n"
        "## Evidence Citations\n"
        "- [1] [Source](https://example.com)"
    )
    handoff_context = (
        "The email-specialist agent has completed their work and handed off to you.\n\n"
        "Summary of their findings:\n"
        "Subject: Broken summary\n\n"
        "Your task: Send the cited email draft produced by the previous step."
    )

    result = module._dispatch_step(
        step,
        {
            "Email Specialist": email_draft,
            "__handoff_context": handoff_context,
            "recipient": "ssebowadisan1@gmail.com",
        },
        "tenant_1",
        "run_delivery_2",
        on_event=lambda event: None,
    )

    assert sent_payload["subject"] == "Machine Learning Research Brief"
    assert "handed off to you" not in sent_payload["body_text"]
    assert result.startswith("To: ssebowadisan1@gmail.com")


def test_dispatch_step_skips_gmail_send_approval_for_direct_mailer_path(monkeypatch) -> None:
    step = WorkflowStep(
        step_id="step_3",
        step_type="agent",
        agent_id="delivery-specialist",
        description="Send the cited email draft produced by the previous step to ssebowadisan1@gmail.com without changing its substance.",
        output_key="output_step_3",
        step_config={"tool_ids": ["gmail.draft", "gmail.send", "mailer.report_send"]},
    )

    approval_tool_ids: list[str] = []

    def _fake_requires_approval(tool_id: str, tenant_id: str = "") -> bool:
        approval_tool_ids.append(tool_id)
        return tool_id == "gmail.send"

    monkeypatch.setitem(
        sys.modules,
        "api.services.agent.approval_workflows",
        SimpleNamespace(
            get_approval_service=lambda: SimpleNamespace(
                requires_approval=_fake_requires_approval,
                create_gate=lambda **kwargs: (_ for _ in ()).throw(AssertionError("approval gate should not be created")),
            )
        ),
    )
    monkeypatch.setattr(module, "_run_direct_delivery_step", lambda **kwargs: "sent output")

    result = module._dispatch_step(
        step,
        {
            "writer": "Subject: Brief\n\nBody [1]",
            "recipient": "ssebowadisan1@gmail.com",
        },
        "tenant_1",
        "run_direct_delivery_no_gate",
        on_event=lambda event: None,
    )

    assert result == "sent output"
    assert approval_tool_ids == ["mailer.report_send"]


def test_run_agent_step_respects_explicit_step_tool_scope(monkeypatch) -> None:
    fake_record = SimpleNamespace(agent_id="research-specialist")
    fake_schema = SimpleNamespace(
        system_prompt="",
        tools=["marketing.web_research"],
        max_tool_calls_per_run=None,
    )

    def _fake_get_agent(tenant_id: str, agent_id: str):
        return fake_record

    def _fake_load_schema(record):
        return fake_schema

    observed: dict[str, object] = {}

    def _fake_run_agent_task(task, *args, **kwargs):
        observed["allowed_tool_ids"] = kwargs.get("allowed_tool_ids")
        yield {"type": "chat_delta", "delta": "done", "text": "done"}

    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.definition_store",
        SimpleNamespace(get_agent=_fake_get_agent, load_schema=_fake_load_schema),
    )
    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.runner",
        SimpleNamespace(run_agent_task=_fake_run_agent_task),
    )
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)

    step = WorkflowStep(
        step_id="step_1",
        step_type="agent",
        agent_id="research-specialist",
        description="Research machine learning and produce a cited summary brief.",
        output_key="research_output",
        step_config={"tool_ids": ["marketing.web_research"]},
    )

    result = module._run_agent_step(
        "research-specialist",
        {"message": "make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com"},
        "tenant_1",
        run_id="parent_run_3",
        on_event=lambda event: None,
        step=step,
    )

    assert result == "done"
    assert observed["allowed_tool_ids"] == ["marketing.web_research"]


def test_run_agent_step_appends_activity_citations_when_section_missing(monkeypatch) -> None:
    fake_record = SimpleNamespace(agent_id="research-specialist")
    fake_schema = SimpleNamespace(
        system_prompt="",
        tools=["marketing.web_research", "report.generate"],
        max_tool_calls_per_run=None,
    )

    def _fake_get_agent(tenant_id: str, agent_id: str):
        return fake_record

    def _fake_load_schema(record):
        return fake_schema

    def _fake_run_agent_task(*args, **kwargs):
        yield {
            "type": "activity",
            "event": {
                "event_type": "web_result_opened",
                "event_id": "evt_open_1",
                "run_id": "child_run_1",
                "title": "Open result",
                "detail": "Open openreview paper",
                "timestamp": "2026-01-01T00:00:00Z",
                "data": {
                    "target_url": "https://openreview.net/pdf?id=DqWvxSQ1TK",
                    "run_id": "child_run_1",
                },
                "metadata": {},
            },
        }
        yield {
            "type": "activity",
            "event": {
                "event_type": "web_result_opened",
                "event_id": "evt_open_2",
                "run_id": "child_run_1",
                "title": "Open result",
                "detail": "Open Nature article",
                "timestamp": "2026-01-01T00:00:01Z",
                "data": {
                    "target_url": "https://www.nature.com/articles/s41586-021-03819-2",
                    "run_id": "child_run_1",
                },
                "metadata": {},
            },
        }
        yield {
            "type": "chat_delta",
            "delta": "done",
            "text": (
                "## Executive Summary\n"
                "Machine learning still faces production reliability gaps [1][2]."
            ),
        }

    activity_rows: list[object] = []
    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.definition_store",
        SimpleNamespace(get_agent=_fake_get_agent, load_schema=_fake_load_schema),
    )
    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.runner",
        SimpleNamespace(run_agent_task=_fake_run_agent_task),
    )
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)
    monkeypatch.setattr(
        "api.services.agent.activity.get_activity_store",
        lambda: SimpleNamespace(
            append=lambda event: activity_rows.append(event),
            load_events=lambda run_id: [{"type": "event", "payload": event.to_dict()} for event in activity_rows],
        ),
    )

    step = WorkflowStep(
        step_id="step_1",
        step_type="agent",
        agent_id="research-specialist",
        description="Research machine learning and produce a cited executive brief.",
        output_key="research_output",
        step_config={"tool_ids": ["marketing.web_research", "report.generate"]},
    )

    result = module._run_agent_step(
        "research-specialist",
        {"task": "research machine learning"},
        "tenant_1",
        run_id="parent_run_citations",
        on_event=lambda event: None,
        step=step,
    )

    assert "## Evidence Citations" in result
    assert "[Openreview.Net]" not in result
    assert "openreview.net" in result.lower()
    assert "nature.com" in result.lower()


def test_run_agent_step_can_append_report_generate_when_scope_is_not_explicit(monkeypatch) -> None:
    fake_record = SimpleNamespace(agent_id="research-specialist")
    fake_schema = SimpleNamespace(
        system_prompt="",
        tools=["marketing.web_research"],
        max_tool_calls_per_run=None,
    )

    def _fake_get_agent(tenant_id: str, agent_id: str):
        return fake_record

    def _fake_load_schema(record):
        return fake_schema

    observed: dict[str, object] = {}

    def _fake_run_agent_task(task, *args, **kwargs):
        observed["allowed_tool_ids"] = kwargs.get("allowed_tool_ids")
        yield {"type": "chat_delta", "delta": "done", "text": "done"}

    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.definition_store",
        SimpleNamespace(get_agent=_fake_get_agent, load_schema=_fake_load_schema),
    )
    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.runner",
        SimpleNamespace(run_agent_task=_fake_run_agent_task),
    )
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)

    step = WorkflowStep(
        step_id="step_1",
        step_type="agent",
        agent_id="research-specialist",
        description="Research machine learning and produce a cited summary brief.",
        output_key="research_output",
        step_config={},
    )

    result = module._run_agent_step(
        "research-specialist",
        {"message": "make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com"},
        "tenant_1",
        run_id="parent_run_4",
        on_event=lambda event: None,
        step=step,
    )

    assert result == "done"
    assert observed["allowed_tool_ids"] == ["marketing.web_research", "report.generate"]


def test_run_agent_step_uses_terminal_agent_run_result_answer(monkeypatch) -> None:
    fake_record = SimpleNamespace(agent_id="research-specialist")
    fake_schema = SimpleNamespace(
        system_prompt="",
        tools=["marketing.web_research"],
        max_tool_calls_per_run=None,
    )

    def _fake_get_agent(tenant_id: str, agent_id: str):
        return fake_record

    def _fake_load_schema(record):
        return fake_schema

    def _fake_run_agent_task(task, *args, **kwargs):
        yield {"type": "activity", "event": {"event_type": "planning_started", "title": "Planning", "detail": ""}}
        yield {
            "event_type": "agent_run_result",
            "content": "Machine learning is a field of AI that learns from data. [1]\n\n### Sources\n- [1] https://example.com/ml",
            "run_result": {"answer": "Machine learning is a field of AI that learns from data. [1]"},
        }

    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.definition_store",
        SimpleNamespace(get_agent=_fake_get_agent, load_schema=_fake_load_schema),
    )
    monkeypatch.setitem(
        sys.modules,
        "api.services.agents.runner",
        SimpleNamespace(run_agent_task=_fake_run_agent_task),
    )
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)
    monkeypatch.setattr(
        "api.services.agent.activity.get_activity_store",
        lambda: SimpleNamespace(append=lambda event: None),
    )

    result = module._run_agent_step(
        "research-specialist",
        {"task": "research machine learning"},
        "tenant_1",
        run_id="parent_run_result_1",
        on_event=lambda event: None,
    )

    assert "Machine learning is a field of AI that learns from data" in result


def test_run_brain_review_uses_lightweight_revision_callbacks(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def _fake_brain_review_loop(**kwargs):
        observed["has_revise_output_fn"] = callable(kwargs.get("revise_output_fn"))
        observed["has_answer_question_fn"] = callable(kwargs.get("answer_question_fn"))
        revised = kwargs["revise_output_fn"]("Fix the citation formatting.", kwargs["initial_output"], 1)
        return revised, [{"decision": "revise"}]

    monkeypatch.setitem(
        sys.modules,
        "api.services.agent.brain.review_loop",
        SimpleNamespace(brain_review_loop=_fake_brain_review_loop),
    )
    monkeypatch.setitem(
        sys.modules,
        "api.services.agent.brain.team_chat",
        SimpleNamespace(
            get_team_chat_service=lambda: SimpleNamespace(
                start_conversation=lambda **kwargs: object(),
                brain_facilitates=lambda **kwargs: [],
            )
        ),
    )
    monkeypatch.setattr(module, "_run_dialogue_detection", lambda **kwargs: kwargs["output"])
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)
    monkeypatch.setattr(
        module,
        "_rewrite_stage_output_with_llm",
        lambda **kwargs: "## Executive Summary\nRevised ML brief with cleaned citations [1].",
    )

    step = WorkflowStep(
        step_id="step_1",
        step_type="agent",
        agent_id="research-specialist",
        description="Research machine learning and produce a cited summary brief.",
        output_key="research_output",
        step_config={"tool_ids": ["marketing.web_research"]},
    )

    result = module._run_brain_review(
        step=step,
        result=(
            "Draft ML answer with weak citations. "
            "This version is intentionally long enough to trigger workflow review "
            "and exercise the lightweight revision callback path."
        ),
        step_inputs={"message": "make the research about machine learning"},
        tenant_id="tenant_1",
        run_id="run_review_1",
        on_event=lambda event: None,
    )

    assert observed["has_revise_output_fn"] is True
    assert observed["has_answer_question_fn"] is True
    assert "Revised ML brief" in result


def test_run_brain_review_does_not_append_team_chat_to_output(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "api.services.agent.brain.review_loop",
        SimpleNamespace(brain_review_loop=lambda **kwargs: ("Reviewed output", [])),
    )
    monkeypatch.setitem(
        sys.modules,
        "api.services.agent.brain.team_chat",
        SimpleNamespace(
            get_team_chat_service=lambda: SimpleNamespace(
                start_conversation=lambda **kwargs: object(),
                brain_facilitates=lambda **kwargs: [
                    SimpleNamespace(speaker_id="writer", speaker_name="Writer", content="Check the claim wording."),
                    SimpleNamespace(speaker_id="brain", speaker_name="Brain", content="Keep it grounded."),
                ],
            )
        ),
    )
    monkeypatch.setattr(module, "_run_dialogue_detection", lambda **kwargs: kwargs["output"])

    step = WorkflowStep(
        step_id="step_1",
        step_type="agent",
        agent_id="research-specialist",
        description="Research machine learning and produce a cited summary brief.",
        output_key="research_output",
        step_config={"tool_ids": ["marketing.web_research"]},
    )

    result = module._run_brain_review(
        step=step,
        result="Reviewed output",
        step_inputs={"message": "make the research about machine learning"},
        tenant_id="tenant_1",
        run_id="run_review_2",
        on_event=lambda event: None,
    )

    assert result == "Reviewed output"
    assert "-- Team Discussion --" not in result


def test_normalize_numbered_citation_section_renumbers_and_drops_orphans() -> None:
    text = (
        "Executive Summary\n\n"
        "Machine learning improves forecast quality in structured settings [1][3], "
        "but deployment costs remain material [4].\n\n"
        "## Evidence Citations\n"
        "- [1] [MLPerf Inference v4.0](https://mlcommons.org/benchmarks/inference)\n"
        "- [2] [Unused source](https://example.com/unused)\n"
        "- [3] [Stanford AI Index 2025](https://hai.stanford.edu/ai-index)\n"
    )

    normalized = module._normalize_numbered_citation_section(text)

    assert "[4]" not in normalized
    assert "- [2] [Unused source](https://example.com/unused)" not in normalized
    assert "Machine learning improves forecast quality in structured settings [1][2]" in normalized
    assert "deployment costs remain material" in normalized
    assert "- [1] [MLPerf Inference v4.0](https://mlcommons.org/benchmarks/inference)" in normalized
    assert "- [2] [Stanford AI Index 2025](https://hai.stanford.edu/ai-index)" in normalized


def test_run_brain_review_skips_dialogue_when_review_rounds_exhausted(monkeypatch) -> None:
    dialogue_called = {"value": False}

    def _fake_brain_review_loop(**kwargs):
        return (
            "Reviewed output with citations [1].\n\n## Evidence Citations\n- [1] [Source](https://example.com/source)",
            [
                {"decision": "revise"},
                {"decision": "revise"},
                {"decision": "revise"},
            ],
        )

    monkeypatch.setitem(
        sys.modules,
        "api.services.agent.brain.review_loop",
        SimpleNamespace(brain_review_loop=_fake_brain_review_loop),
    )
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)

    def _fake_dialogue_detection(**kwargs):
        dialogue_called["value"] = True
        return kwargs["output"]

    monkeypatch.setattr(module, "_run_dialogue_detection", _fake_dialogue_detection)

    step = WorkflowStep(
        step_id="step_1",
        step_type="agent",
        agent_id="research-specialist",
        description="Research machine learning and produce a cited summary brief.",
        output_key="research_output",
        step_config={"tool_ids": ["marketing.web_research"]},
    )

    result = module._run_brain_review(
        step=step,
        result="Initial output with citations [1].\n\n## Evidence Citations\n- [1] [Source](https://example.com/source)",
        step_inputs={"message": "make the research about machine learning"},
        tenant_id="tenant_1",
        run_id="run_review_3",
        on_event=lambda event: None,
    )

    assert dialogue_called["value"] is False
    assert "## Evidence Citations" in result


def test_compact_research_brief_output_rewrites_long_report(monkeypatch) -> None:
    step = WorkflowStep(
        step_id="step_1",
        step_type="agent",
        agent_id="research-specialist",
        description=(
            "Research machine learning using multiple authoritative sources and extract source-backed findings with inline citations. "
            "Return a concise executive research brief with short headings, a premium polished tone, and a final Evidence Citations section. "
            "Do not draft or send the email."
        ),
        output_key="output_step_1",
        step_config={"tool_ids": ["marketing.web_research", "web.extract.structured", "report.generate"]},
    )
    long_result = (
        "## Executive Summary\n"
        "Machine learning improves predictions and automation across industries [1][2]. "
        "It also introduces governance, data quality, and scaling demands that slow deployment [3][4].\n\n"
        "## Adoption Realities\n"
        + ("Repeated supporting detail [1][2][3]. " * 45)
        + "\n\n## Platform Landscape\n"
        + ("More platform detail [2][4]. " * 30)
        + "\n\n## Evidence Citations\n"
        "- [1] IBM (https://example.com/ibm)\n"
        "- [2] Gartner (https://example.com/gartner)\n"
        "- [3] McKinsey (https://example.com/mckinsey)\n"
        "- [4] Enterprisers Project (https://example.com/enterprisers)"
    )
    compact_result = (
        "## Executive Summary\n"
        "Machine learning turns data into predictive decisions and process automation, but value only scales when governance, "
        "data quality, and operating discipline are in place [1][3]. Enterprise ROI is strongest when ML is embedded in a broader "
        "AI strategy rather than treated as an isolated pilot [1][2]. Adoption friction still clusters around use-case prioritization, "
        "talent, and production readiness [2][4].\n\n"
        "## Evidence Citations\n"
        "- [1] IBM (https://example.com/ibm)\n"
        "- [2] Gartner (https://example.com/gartner)\n"
        "- [3] McKinsey (https://example.com/mckinsey)\n"
        "- [4] Enterprisers Project (https://example.com/enterprisers)"
    )

    monkeypatch.setattr(module, "_rewrite_stage_output_with_llm", lambda **kwargs: compact_result)
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)

    result = module._compact_research_brief_output(
        step=step,
        step_inputs={"query": "machine learning"},
        result=long_result,
        tenant_id="tenant_1",
    )

    assert result == compact_result
