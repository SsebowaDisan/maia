import html
import os
import zipfile
from pathlib import Path

import gradio as gr
from ktem.db.engine import engine
from ktem.utils.render import Render
from sqlalchemy import select
from sqlalchemy.orm import Session
from theflow.settings import settings as flowsettings

from .constants import DOWNLOAD_MESSAGE


class FileIndexActionsMixin:
    def file_selected(self, file_id):
        chunks = []
        if file_id is not None:
            Index = self._index._resources["Index"]
            with Session(engine) as session:
                matches = session.execute(
                    select(Index).where(
                        Index.source_id == file_id,
                        Index.relation_type == "document",
                    )
                )
                doc_ids = [doc.target_id for (doc,) in matches]
                docs = self._index._docstore.get(doc_ids)
                docs = sorted(
                    docs, key=lambda x: x.metadata.get("page_label", float("inf"))
                )

                for idx, doc in enumerate(docs):
                    title = html.escape(
                        f"{doc.text[:50]}..." if len(doc.text) > 50 else doc.text
                    )
                    doc_type = doc.metadata.get("type", "text")
                    content = ""
                    if doc_type == "text":
                        content = html.escape(doc.text)
                    elif doc_type == "table":
                        content = Render.table(doc.text)
                    elif doc_type == "image":
                        content = Render.image(
                            url=doc.metadata.get("image_origin", ""), text=doc.text
                        )

                    header_prefix = f"[{idx+1}/{len(docs)}]"
                    if doc.metadata.get("page_label"):
                        header_prefix += f" [Page {doc.metadata['page_label']}]"

                    chunks.append(
                        Render.collapsible(
                            header=f"{header_prefix} {title}",
                            content=content,
                        )
                    )
        return (
            gr.update(value="".join(chunks), visible=file_id is not None),
            gr.update(visible=file_id is not None),
            gr.update(visible=file_id is not None),
            gr.update(visible=file_id is not None),
            gr.update(visible=file_id is not None),
        )

    def delete_event(self, file_id):
        file_name = ""
        with Session(engine) as session:
            source = session.execute(
                select(self._index._resources["Source"]).where(
                    self._index._resources["Source"].id == file_id
                )
            ).first()
            if source:
                file_name = source[0].name
                session.delete(source[0])

            vs_ids, ds_ids = [], []
            index = session.execute(
                select(self._index._resources["Index"]).where(
                    self._index._resources["Index"].source_id == file_id
                )
            ).all()
            for each in index:
                if each[0].relation_type == "vector":
                    vs_ids.append(each[0].target_id)
                elif each[0].relation_type == "document":
                    ds_ids.append(each[0].target_id)
                session.delete(each[0])
            session.commit()

        if vs_ids:
            self._index._vs.delete(vs_ids)
        self._index._docstore.delete(ds_ids)

        gr.Info(f"File {file_name} has been deleted")
        return None, self.selected_panel_false

    def delete_no_event(self):
        return (
            gr.update(visible=True),
            gr.update(visible=False),
        )

    def download_single_file(self, is_zipped_state, file_id):
        with Session(engine) as session:
            source = session.execute(
                select(self._index._resources["Source"]).where(
                    self._index._resources["Source"].id == file_id
                )
            ).first()
        if source:
            target_file_name = Path(source[0].name)
        zip_files = []
        for file_name in os.listdir(flowsettings.KH_CHUNKS_OUTPUT_DIR):
            if target_file_name.stem in file_name:
                zip_files.append(
                    os.path.join(flowsettings.KH_CHUNKS_OUTPUT_DIR, file_name)
                )
        for file_name in os.listdir(flowsettings.KH_MARKDOWN_OUTPUT_DIR):
            if target_file_name.stem in file_name:
                zip_files.append(
                    os.path.join(flowsettings.KH_MARKDOWN_OUTPUT_DIR, file_name)
                )
        zip_file_path = os.path.join(
            flowsettings.KH_ZIP_OUTPUT_DIR, target_file_name.stem
        )
        with zipfile.ZipFile(f"{zip_file_path}.zip", "w") as zip_me:
            for file in zip_files:
                zip_me.write(file, arcname=os.path.basename(file))

        if is_zipped_state:
            new_button = gr.DownloadButton(label="Download", value=None)
        else:
            new_button = gr.DownloadButton(
                label=DOWNLOAD_MESSAGE, value=f"{zip_file_path}.zip"
            )

        return not is_zipped_state, new_button

    def download_single_file_simple(self, is_zipped_state, file_html, file_id):
        with Session(engine) as session:
            source = session.execute(
                select(self._index._resources["Source"]).where(
                    self._index._resources["Source"].id == file_id
                )
            ).first()
        if source:
            target_file_name = Path(source[0].name)

        output_file_path = os.path.join(
            flowsettings.KH_ZIP_OUTPUT_DIR, target_file_name.stem + ".html"
        )
        with open(output_file_path, "w") as file:
            file.write(file_html)

        if is_zipped_state:
            new_button = gr.DownloadButton(label="Download", value=None)
        else:
            new_button = gr.DownloadButton(
                label=DOWNLOAD_MESSAGE,
                value=output_file_path,
            )

        return not is_zipped_state, new_button

    def download_all_files(self):
        if self._index.config.get("private", False):
            raise gr.Error("This feature is not available for private collection.")

        zip_files = []
        for file_name in os.listdir(flowsettings.KH_CHUNKS_OUTPUT_DIR):
            zip_files.append(os.path.join(flowsettings.KH_CHUNKS_OUTPUT_DIR, file_name))
        for file_name in os.listdir(flowsettings.KH_MARKDOWN_OUTPUT_DIR):
            zip_files.append(
                os.path.join(flowsettings.KH_MARKDOWN_OUTPUT_DIR, file_name)
            )
        zip_file_path = os.path.join(flowsettings.KH_ZIP_OUTPUT_DIR, "all")
        with zipfile.ZipFile(f"{zip_file_path}.zip", "w") as zip_me:
            for file in zip_files:
                arcname = Path(file)
                zip_me.write(file, arcname=arcname.name)
        return gr.DownloadButton(label=DOWNLOAD_MESSAGE, value=f"{zip_file_path}.zip")

    def delete_all_files(self, file_list):
        for file_id in file_list.id.values:
            self.delete_event(file_id)

    def set_file_id_selector(self, selected_file_id):
        return [selected_file_id, "select", gr.Tabs(selected="chat-tab")]

    def show_delete_all_confirm(self, file_list):
        if len(file_list) == 0 or (
            len(file_list) == 1 and file_list.id.values[0] == "-"
        ):
            gr.Info("No file to delete")
            return [
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
            ]
        else:
            return [
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=True),
            ]
