import json

import gradio as gr
from ktem.app import BasePage
from ktem.db.engine import engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from .constants import KH_DEMO_MODE, MAX_FILE_COUNT, update_file_list_js


class FileSelector(BasePage):
    """File selector UI in the Chat page."""

    def __init__(self, app, index):
        super().__init__(app)
        self._index = index
        self.on_building_ui()

    def default(self):
        if self._app.f_user_management:
            return "disabled", [], -1
        return "disabled", [], 1

    def on_building_ui(self):
        default_mode, default_selector, user_id = self.default()

        self.mode = gr.Radio(
            value=default_mode,
            choices=[
                ("Search All", "all"),
                ("Search In File(s)", "select"),
            ],
            container=False,
        )
        self.selector = gr.Dropdown(
            label="Files",
            value=default_selector,
            choices=[],
            multiselect=True,
            container=False,
            interactive=True,
            visible=False,
        )
        self.selector_user_id = gr.State(value=user_id)
        self.selector_choices = gr.JSON(
            value=[],
            visible=False,
        )

    def on_register_events(self):
        self.mode.change(
            fn=lambda mode, user_id: (gr.update(visible=mode == "select"), user_id),
            inputs=[self.mode, self._app.user_id],
            outputs=[self.selector, self.selector_user_id],
        )
        if self._index.id == 1:
            self.selector_choices.change(
                fn=None,
                inputs=[self.selector_choices],
                js=update_file_list_js,
                show_progress="hidden",
            )

    def as_gradio_component(self):
        return [self.mode, self.selector, self.selector_user_id]

    def get_selected_ids(self, components):
        mode, selected, user_id = components[0], components[1], components[2]
        if user_id is None:
            return []

        if mode == "disabled":
            return []
        elif mode == "select":
            return selected

        file_ids = []
        with Session(engine) as session:
            statement = select(self._index._resources["Source"].id)
            if self._index.config.get("private", False):
                statement = statement.where(
                    self._index._resources["Source"].user == user_id
                )
            results = session.execute(statement).all()
            for (id_,) in results:
                file_ids.append(id_)

        return file_ids

    def load_files(self, selected_files, user_id):
        options: list = []
        available_ids = []
        if user_id is None:
            return gr.update(value=selected_files, choices=options), options

        with Session(engine) as session:
            statement = select(self._index._resources["Source"])
            if self._index.config.get("private", False):
                statement = statement.where(
                    self._index._resources["Source"].user == user_id
                )

            if KH_DEMO_MODE:
                statement = statement.limit(MAX_FILE_COUNT)

            results = session.execute(statement).all()
            for result in results:
                available_ids.append(result[0].id)
                options.append((result[0].name, result[0].id))

            FileGroup = self._index._resources["FileGroup"]
            statement = select(FileGroup)
            if self._index.config.get("private", False):
                statement = statement.where(FileGroup.user == user_id)
            results = session.execute(statement).all()
            for result in results:
                item = result[0]
                options.append(
                    (f"group: '{item.name}'", json.dumps(item.data.get("files", [])))
                )

        if selected_files:
            available_ids_set = set(available_ids)
            selected_files = [
                each for each in selected_files if each in available_ids_set
            ]

        return gr.update(value=selected_files, choices=options), options

    def _on_app_created(self):
        self._app.app.load(
            self.load_files,
            inputs=[self.selector, self._app.user_id],
            outputs=[self.selector, self.selector_choices],
        )

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name=f"onFileIndex{self._index.id}Changed",
            definition={
                "fn": self.load_files,
                "inputs": [self.selector, self._app.user_id],
                "outputs": [self.selector, self.selector_choices],
                "show_progress": "hidden",
            },
        )
        if self._app.f_user_management:
            for event_name in ["onSignIn", "onSignOut"]:
                self._app.subscribe_event(
                    name=event_name,
                    definition={
                        "fn": self.load_files,
                        "inputs": [self.selector, self._app.user_id],
                        "outputs": [self.selector, self.selector_choices],
                        "show_progress": "hidden",
                    },
                )
