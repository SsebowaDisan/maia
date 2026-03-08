import gradio as gr

from .constants import chat_input_focus_js_with_submit

WAIT_FOR_INDEXING_MESSAGE = (
    "Please wait for the indexing process to complete before adding your question."
)


def file_index_change_event_name(owner) -> str:
    return f"onFileIndex{owner._index.id}Changed"


def apply_file_index_change_events(owner, event_chain):
    for event in owner._app.get_event(file_index_change_event_name(owner)):
        event_chain = event_chain.then(**event)
    return event_chain


def subscribe_signin_signout_events(owner) -> None:
    owner._app.subscribe_event(
        name="onSignIn",
        definition={
            "fn": owner.list_file,
            "inputs": [owner._app.user_id],
            "outputs": [owner.file_list_state, owner.file_list],
            "show_progress": "hidden",
        },
    )
    owner._app.subscribe_event(
        name="onSignIn",
        definition={
            "fn": owner.list_group,
            "inputs": [owner._app.user_id, owner.file_list_state],
            "outputs": [owner.group_list_state, owner.group_list],
            "show_progress": "hidden",
        },
    )
    owner._app.subscribe_event(
        name="onSignIn",
        definition={
            "fn": owner.list_file_names,
            "inputs": [owner.file_list_state],
            "outputs": [owner.group_files],
            "show_progress": "hidden",
        },
    )
    owner._app.subscribe_event(
        name="onSignOut",
        definition={
            "fn": owner.list_file,
            "inputs": [owner._app.user_id],
            "outputs": [owner.file_list_state, owner.file_list],
            "show_progress": "hidden",
        },
    )


def focus_chat_input_event(owner, event_chain):
    return event_chain.then(
        fn=lambda: True,
        inputs=None,
        outputs=None,
        js=chat_input_focus_js_with_submit,
    )


def wait_for_indexing_update():
    return gr.update(value=WAIT_FOR_INDEXING_MESSAGE)


def clear_uploaded_selector():
    return [
        gr.update(value=None),
        gr.update(value="select"),
    ]


def hide_delete_all_controls():
    return [
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False),
    ]


def clear_upload_progress_panel():
    return (gr.update(visible=False), "", "")


def open_group_panel_updates():
    return (
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(visible=True),
        gr.update(visible=True),
    )


def prepare_group_create_updates():
    return [
        gr.update(visible=False),
        gr.update(value="### Add new group"),
        gr.update(visible=True),
        gr.update(value=""),
        gr.update(value=[]),
        None,
    ]


def close_group_panel_updates():
    return [
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        None,
    ]
