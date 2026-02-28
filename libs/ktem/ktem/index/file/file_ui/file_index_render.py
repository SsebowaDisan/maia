import gradio as gr

from .constants import KH_SSO_ENABLED
from .file_upload import File


class FileIndexRenderMixin:
    def upload_instruction(self) -> str:
        msgs = []
        if self._supported_file_types:
            msgs.append(f"- Supported file types: {self._supported_file_types_str}")

        if max_file_size := self._index.config.get("max_file_size", 0):
            msgs.append(f"- Maximum file size: {max_file_size} MB")

        if max_number_of_files := self._index.config.get("max_number_of_files", 0):
            msgs.append(f"- The index can have maximum {max_number_of_files} files")

        if msgs:
            return "\n".join(msgs)

        return ""

    def render_file_list(self):
        self.filter = gr.Textbox(
            value="",
            label="Filter by name:",
            info=(
                "(1) Case-insensitive. "
                "(2) Search with empty string to show all files."
            ),
        )
        self.file_list_state = gr.State(value=None)
        self.file_list = gr.DataFrame(
            headers=["id", "name", "size", "tokens", "loader", "date_created"],
            column_widths=["0%", "50%", "8%", "7%", "15%", "20%"],
            interactive=False,
            wrap=False,
            elem_id="file_list_view",
        )

        with gr.Row():
            self.chat_button = gr.Button("Go to Chat", visible=False)
            self.is_zipped_state = gr.State(value=False)
            self.download_single_button = gr.DownloadButton("Download", visible=False)
            self.delete_button = gr.Button("Delete", variant="stop", visible=False)
            self.deselect_button = gr.Button("Close", visible=False)

        with gr.Row() as self.selection_info:
            self.selected_file_id = gr.State(value=None)
            with gr.Column(scale=2):
                self.selected_panel = gr.Markdown(self.selected_panel_false)

        self.chunks = gr.HTML(visible=False)

        with gr.Accordion("Advance options", open=False):
            with gr.Row():
                if not KH_SSO_ENABLED:
                    self.download_all_button = gr.DownloadButton("Download all files")
                self.delete_all_button = gr.Button(
                    "Delete all files",
                    variant="stop",
                    visible=True,
                )
                self.delete_all_button_confirm = gr.Button(
                    "Confirm delete", variant="stop", visible=False
                )
                self.delete_all_button_cancel = gr.Button("Cancel", visible=False)

    def render_group_list(self):
        self.group_list_state = gr.State(value=None)
        self.group_list = gr.DataFrame(
            headers=["id", "name", "files", "date_created"],
            column_widths=["0%", "25%", "55%", "20%"],
            interactive=False,
            wrap=False,
        )

        with gr.Row():
            self.group_add_button = gr.Button("Add", variant="primary")
            self.group_chat_button = gr.Button("Go to Chat", visible=False)
            self.group_delete_button = gr.Button("Delete", variant="stop", visible=False)
            self.group_close_button = gr.Button("Close", visible=False)

        with gr.Column(visible=False) as self._group_info_panel:
            self.selected_group_id = gr.State(value=None)
            self.group_label = gr.Markdown()
            self.group_name = gr.Textbox(
                label="Group name",
                placeholder="Group name",
                lines=1,
                max_lines=1,
            )
            self.group_files = gr.Dropdown(
                label="Attached files",
                multiselect=True,
            )
            self.group_save_button = gr.Button("Save", variant="primary")

    def on_building_ui(self):
        with gr.Row():
            with gr.Column(scale=1):
                with gr.Column() as self.upload:
                    with gr.Tab("Upload Files"):
                        self.files = File(
                            file_types=self._supported_file_types,
                            file_count="multiple",
                            container=True,
                            show_label=False,
                        )

                        msg = self.upload_instruction()
                        if msg:
                            gr.Markdown(msg)

                    with gr.Tab("Use Web Links"):
                        self.urls = gr.Textbox(label="Input web URLs", lines=8)
                        gr.Markdown("(separated by new line)")

                    with gr.Accordion("Advanced indexing options", open=False):
                        with gr.Row():
                            self.reindex = gr.Checkbox(
                                value=False, label="Force reindex file", container=False
                            )

                    self.upload_button = gr.Button("Upload and Index", variant="primary")

            with gr.Column(scale=4):
                with gr.Column(visible=False) as self.upload_progress_panel:
                    gr.Markdown("## Upload Progress")
                    with gr.Row():
                        self.upload_result = gr.Textbox(
                            lines=1, max_lines=20, label="Upload result"
                        )
                        self.upload_info = gr.Textbox(
                            lines=1, max_lines=20, label="Upload info"
                        )
                    self.btn_close_upload_progress_panel = gr.Button(
                        "Clear Upload Info and Close",
                        variant="secondary",
                        elem_classes=["right-button"],
                    )

                with gr.Tab("Files"):
                    self.render_file_list()

                with gr.Tab("Groups"):
                    self.render_group_list()
