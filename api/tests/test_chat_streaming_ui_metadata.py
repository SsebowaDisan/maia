from api.services.chat.streaming import make_activity_stream_event
import api.services.chat.streaming as chat_streaming


def test_make_activity_stream_event_emits_browser_ui_commit() -> None:
    event = make_activity_stream_event(
        run_id="run-1",
        event_type="browser_navigate",
        title="Navigate browser",
        detail="Opening page",
        data={
            "scene_surface": "website",
            "url": "https://example.org",
        },
        seq=1,
    )
    payload = event["data"]
    assert payload.get("ui_target") == "browser"
    assert payload.get("ui_stage") in {"execute", "surface"}
    ui_commit = payload.get("ui_commit")
    assert isinstance(ui_commit, dict)
    assert ui_commit.get("surface") == "browser"
    assert ui_commit.get("url") == "https://example.org"


def test_make_activity_stream_event_marks_done_stage_for_response_written() -> None:
    event = make_activity_stream_event(
        run_id="run-2",
        event_type="response_written",
        title="Response complete",
        detail="Prepared final response",
        seq=2,
    )
    payload = event["data"]
    assert payload.get("ui_stage") == "done"
    assert payload.get("ui_target") == "system"


def test_make_activity_stream_event_emits_api_commit_on_api_family_events() -> None:
    event = make_activity_stream_event(
        run_id="run-3",
        event_type="api_request_completed",
        title="API request completed",
        detail="Connector request finished",
        data={
            "event_family": "api",
        },
        seq=3,
    )
    payload = event["data"]
    ui_commit = payload.get("ui_commit")
    assert payload.get("ui_target") == "system"
    assert isinstance(ui_commit, dict)
    assert ui_commit.get("surface") == "api"


def test_make_activity_stream_event_emits_document_commit_for_sheet_url() -> None:
    event = make_activity_stream_event(
        run_id="run-4",
        event_type="sheets.update",
        title="Update sheet",
        data={"scene_surface": "google_sheets", "spreadsheet_url": "https://docs.google.com/spreadsheets/d/123/edit"},
        seq=4,
    )
    payload = event["data"]
    ui_commit = payload.get("ui_commit")
    assert payload.get("ui_target") == "document"
    assert isinstance(ui_commit, dict)
    assert ui_commit.get("surface") == "document"
    assert ui_commit.get("commit") == "open_sheet"


def test_make_activity_stream_event_emits_email_commit_for_email_events() -> None:
    event = make_activity_stream_event(
        run_id="run-5",
        event_type="email_set_subject",
        title="Set subject",
        detail="Quarterly summary",
        data={"scene_surface": "email"},
        seq=5,
    )
    payload = event["data"]
    ui_commit = payload.get("ui_commit")
    assert payload.get("ui_target") == "email"
    assert isinstance(ui_commit, dict)
    assert ui_commit.get("surface") == "email"


def test_make_activity_stream_event_omits_ui_fields_when_staged_theatre_disabled() -> None:
    previous = chat_streaming.STAGED_THEATRE_ENABLED
    chat_streaming.STAGED_THEATRE_ENABLED = False
    try:
        event = make_activity_stream_event(
            run_id="run-6",
            event_type="browser_navigate",
            title="Navigate",
            data={"scene_surface": "website", "url": "https://example.org"},
            seq=6,
        )
    finally:
        chat_streaming.STAGED_THEATRE_ENABLED = previous

    payload = event["data"]
    assert payload.get("ui_stage") is None
    assert payload.get("ui_target") is None
    assert payload.get("ui_commit") is None
