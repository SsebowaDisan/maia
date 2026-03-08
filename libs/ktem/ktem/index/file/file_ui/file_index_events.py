import gradio as gr

from .constants import KH_DEMO_MODE, KH_SSO_ENABLED
from .event_helpers import (
    apply_file_index_change_events,
    clear_upload_progress_panel,
    clear_uploaded_selector,
    close_group_panel_updates,
    focus_chat_input_event,
    hide_delete_all_controls,
    open_group_panel_updates,
    prepare_group_create_updates,
    subscribe_signin_signout_events,
    wait_for_indexing_update,
)


class FileIndexEventMixin:
    def on_subscribe_public_events(self):
        if KH_DEMO_MODE:
            return

        self._app.subscribe_event(
            name=f"onFileIndex{self._index.id}Changed",
            definition={
                "fn": self.list_file_names,
                "inputs": [self.file_list_state],
                "outputs": [self.group_files],
                "show_progress": "hidden",
            },
        )

        if self._app.f_user_management:
            subscribe_signin_signout_events(self)

    def on_register_quick_uploads(self):
        try:
            if self._index.id == 1:
                self.quick_upload_state = gr.State(value=[])
                print("Setting up quick upload event")

                self._app.chat_page.first_indexing_url_fn = (
                    self.index_fn_url_with_default_loaders
                )

                if not KH_DEMO_MODE:
                    quick_uploaded_event = (
                        self._app.chat_page.quick_file_upload.upload(
                            fn=wait_for_indexing_update,
                            outputs=self._app.chat_page.quick_file_upload_status,
                        )
                        .then(
                            fn=self.index_fn_file_with_default_loaders,
                            inputs=[
                                self._app.chat_page.quick_file_upload,
                                gr.State(value=False),
                                self._app.settings_state,
                                self._app.user_id,
                            ],
                            outputs=self.quick_upload_state,
                            concurrency_limit=10,
                        )
                        .success(
                            fn=clear_uploaded_selector,
                            outputs=[
                                self._app.chat_page.quick_file_upload,
                                self._app.chat_page._indices_input[0],
                            ],
                        )
                    )
                    quick_uploaded_event = apply_file_index_change_events(
                        self,
                        quick_uploaded_event,
                    )

                    quick_uploaded_event = (
                        quick_uploaded_event.success(
                            fn=lambda x: x,
                            inputs=self.quick_upload_state,
                            outputs=self._app.chat_page._indices_input[1],
                        )
                        .then(
                            fn=lambda: gr.update(value="Indexing completed."),
                            outputs=self._app.chat_page.quick_file_upload_status,
                        )
                        .then(
                            fn=self.list_file,
                            inputs=[self._app.user_id, self.filter],
                            outputs=[self.file_list_state, self.file_list],
                            concurrency_limit=20,
                        )
                    )
                    quick_uploaded_event = focus_chat_input_event(
                        self,
                        quick_uploaded_event,
                    )

                quick_url_uploaded_event = (
                    self._app.chat_page.quick_urls.submit(
                        fn=wait_for_indexing_update,
                        outputs=self._app.chat_page.quick_file_upload_status,
                    )
                    .then(
                        fn=self.index_fn_url_with_default_loaders,
                        inputs=[
                            self._app.chat_page.quick_urls,
                            gr.State(value=False),
                            self._app.settings_state,
                            self._app.user_id,
                        ],
                        outputs=self.quick_upload_state,
                        concurrency_limit=10,
                    )
                    .success(
                        fn=clear_uploaded_selector,
                        outputs=[
                            self._app.chat_page.quick_urls,
                            self._app.chat_page._indices_input[0],
                        ],
                    )
                )
                quick_url_uploaded_event = apply_file_index_change_events(
                    self,
                    quick_url_uploaded_event,
                )

                quick_url_uploaded_event = quick_url_uploaded_event.success(
                    fn=lambda x: x,
                    inputs=self.quick_upload_state,
                    outputs=self._app.chat_page._indices_input[1],
                ).then(
                    fn=lambda: gr.update(value="Indexing completed."),
                    outputs=self._app.chat_page.quick_file_upload_status,
                )

                if not KH_DEMO_MODE:
                    quick_url_uploaded_event = quick_url_uploaded_event.then(
                        fn=self.list_file,
                        inputs=[self._app.user_id, self.filter],
                        outputs=[self.file_list_state, self.file_list],
                        concurrency_limit=20,
                    )

                quick_url_uploaded_event = focus_chat_input_event(
                    self,
                    quick_url_uploaded_event,
                )

        except Exception as exc:
            print(exc)

    def on_register_events(self):
        self.on_register_quick_uploads()

        if KH_DEMO_MODE:
            return

        on_deleted = (
            self.delete_button.click(
                fn=self.delete_event,
                inputs=[self.selected_file_id],
                outputs=None,
            )
            .then(
                fn=lambda: (None, self.selected_panel_false),
                inputs=[],
                outputs=[self.selected_file_id, self.selected_panel],
                show_progress="hidden",
            )
            .then(
                fn=self.list_file,
                inputs=[self._app.user_id, self.filter],
                outputs=[self.file_list_state, self.file_list],
            )
            .then(
                fn=self.file_selected,
                inputs=[self.selected_file_id],
                outputs=[
                    self.chunks,
                    self.deselect_button,
                    self.delete_button,
                    self.download_single_button,
                    self.chat_button,
                ],
                show_progress="hidden",
            )
        )
        on_deleted = apply_file_index_change_events(self, on_deleted)

        self.deselect_button.click(
            fn=lambda: (None, self.selected_panel_false),
            inputs=[],
            outputs=[self.selected_file_id, self.selected_panel],
            show_progress="hidden",
        ).then(
            fn=self.file_selected,
            inputs=[self.selected_file_id],
            outputs=[
                self.chunks,
                self.deselect_button,
                self.delete_button,
                self.download_single_button,
                self.chat_button,
            ],
            show_progress="hidden",
        )

        self.chat_button.click(
            fn=self.set_file_id_selector,
            inputs=[self.selected_file_id],
            outputs=[
                self._index.get_selector_component_ui().selector,
                self._index.get_selector_component_ui().mode,
                self._app.tabs,
            ],
        )

        if not KH_SSO_ENABLED:
            self.download_all_button.click(
                fn=self.download_all_files,
                inputs=[],
                outputs=self.download_all_button,
                show_progress="hidden",
            )

        self.delete_all_button.click(
            self.show_delete_all_confirm,
            [self.file_list],
            [
                self.delete_all_button,
                self.delete_all_button_confirm,
                self.delete_all_button_cancel,
            ],
        )
        self.delete_all_button_cancel.click(
            hide_delete_all_controls,
            None,
            [
                self.delete_all_button,
                self.delete_all_button_confirm,
                self.delete_all_button_cancel,
            ],
        )

        self.delete_all_button_confirm.click(
            fn=self.delete_all_files,
            inputs=[self.file_list],
            outputs=[],
            show_progress="hidden",
        ).then(
            fn=self.list_file,
            inputs=[self._app.user_id, self.filter],
            outputs=[self.file_list_state, self.file_list],
        ).then(
            hide_delete_all_controls,
            None,
            [
                self.delete_all_button,
                self.delete_all_button_confirm,
                self.delete_all_button_cancel,
            ],
        )

        if not KH_SSO_ENABLED:
            self.download_single_button.click(
                fn=self.download_single_file,
                inputs=[self.is_zipped_state, self.selected_file_id],
                outputs=[self.is_zipped_state, self.download_single_button],
                show_progress="hidden",
            )
        else:
            self.download_single_button.click(
                fn=self.download_single_file_simple,
                inputs=[self.is_zipped_state, self.chunks, self.selected_file_id],
                outputs=[self.is_zipped_state, self.download_single_button],
                show_progress="hidden",
            )

        on_uploaded = (
            self.upload_button.click(
                fn=lambda: gr.update(visible=True),
                outputs=[self.upload_progress_panel],
            )
            .then(
                fn=self.index_fn,
                inputs=[
                    self.files,
                    self.urls,
                    self.reindex,
                    self._app.settings_state,
                    self._app.user_id,
                ],
                outputs=[self.upload_result, self.upload_info],
                concurrency_limit=20,
            )
            .then(
                fn=lambda: gr.update(value=""),
                outputs=[self.urls],
            )
        )

        uploaded_event = on_uploaded.then(
            fn=self.list_file,
            inputs=[self._app.user_id, self.filter],
            outputs=[self.file_list_state, self.file_list],
            concurrency_limit=20,
        )
        uploaded_event = apply_file_index_change_events(self, uploaded_event)

        _ = on_uploaded.success(
            fn=lambda: None,
            outputs=[self.files],
        )

        self.btn_close_upload_progress_panel.click(
            fn=clear_upload_progress_panel,
            outputs=[self.upload_progress_panel, self.upload_result, self.upload_info],
        )

        self.file_list.select(
            fn=self.interact_file_list,
            inputs=[self.file_list],
            outputs=[self.selected_file_id, self.selected_panel],
            show_progress="hidden",
        ).then(
            fn=self.file_selected,
            inputs=[self.selected_file_id],
            outputs=[
                self.chunks,
                self.deselect_button,
                self.delete_button,
                self.download_single_button,
                self.chat_button,
            ],
            show_progress="hidden",
        )

        self.group_list.select(
            fn=self.interact_group_list,
            inputs=[self.group_list_state],
            outputs=[
                self.group_label,
                self.selected_group_id,
                self.group_name,
                self.group_files,
            ],
            show_progress="hidden",
        ).then(
            fn=open_group_panel_updates,
            outputs=[
                self._group_info_panel,
                self.group_add_button,
                self.group_close_button,
                self.group_delete_button,
                self.group_chat_button,
            ],
        )

        self.filter.submit(
            fn=self.list_file,
            inputs=[self._app.user_id, self.filter],
            outputs=[self.file_list_state, self.file_list],
            show_progress="hidden",
        )

        self.group_add_button.click(
            fn=prepare_group_create_updates,
            outputs=[
                self.group_add_button,
                self.group_label,
                self._group_info_panel,
                self.group_name,
                self.group_files,
                self.selected_group_id,
            ],
        )

        self.group_chat_button.click(
            fn=self.set_group_id_selector,
            inputs=[self.selected_group_id],
            outputs=[
                self._index.get_selector_component_ui().selector,
                self._index.get_selector_component_ui().mode,
                self._app.tabs,
            ],
        )

        on_group_closed_event = {
            "fn": close_group_panel_updates,
            "outputs": [
                self.group_add_button,
                self._group_info_panel,
                self.group_close_button,
                self.group_delete_button,
                self.group_chat_button,
                self.selected_group_id,
            ],
        }
        self.group_close_button.click(**on_group_closed_event)
        on_group_saved = (
            self.group_save_button.click(
                fn=self.save_group,
                inputs=[
                    self.selected_group_id,
                    self.group_name,
                    self.group_files,
                    self._app.user_id,
                ],
            )
            .then(
                self.list_group,
                inputs=[self._app.user_id, self.file_list_state],
                outputs=[self.group_list_state, self.group_list],
            )
            .then(**on_group_closed_event)
        )
        on_group_deleted = (
            self.group_delete_button.click(
                fn=self.delete_group,
                inputs=[self.selected_group_id],
            )
            .then(
                self.list_group,
                inputs=[self._app.user_id, self.file_list_state],
                outputs=[self.group_list_state, self.group_list],
            )
            .then(**on_group_closed_event)
        )

        on_group_deleted = apply_file_index_change_events(self, on_group_deleted)
        on_group_saved = apply_file_index_change_events(self, on_group_saved)

    def _on_app_created(self):
        if KH_DEMO_MODE:
            return

        self._app.app.load(
            self.list_file,
            inputs=[self._app.user_id, self.filter],
            outputs=[self.file_list_state, self.file_list],
        ).then(
            self.list_group,
            inputs=[self._app.user_id, self.file_list_state],
            outputs=[self.group_list_state, self.group_list],
        ).then(
            self.list_file_names,
            inputs=[self.file_list_state],
            outputs=[self.group_files],
        )
