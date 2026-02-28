import json
from copy import deepcopy

import gradio as gr
import pandas as pd
from ktem.db.engine import engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from .constants import MAX_FILENAME_LENGTH


class FileIndexDataMixin:
    def format_size_human_readable(self, num: float | str, suffix="B"):
        try:
            num = float(num)
        except ValueError:
            return num

        for unit in ("", "K", "M", "G", "T", "P", "E", "Z"):
            if abs(num) < 1024.0:
                return f"{num:3.0f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.0f}Yi{suffix}"

    def list_file(self, user_id, name_pattern=""):
        if user_id is None:
            return [], pd.DataFrame.from_records(
                [
                    {
                        "id": "-",
                        "name": "-",
                        "size": "-",
                        "tokens": "-",
                        "loader": "-",
                        "date_created": "-",
                    }
                ]
            )

        Source = self._index._resources["Source"]
        with Session(engine) as session:
            statement = select(Source)
            if self._index.config.get("private", False):
                statement = statement.where(Source.user == user_id)
            if name_pattern:
                statement = statement.where(Source.name.ilike(f"%{name_pattern}%"))
            results = [
                {
                    "id": each[0].id,
                    "name": each[0].name,
                    "size": self.format_size_human_readable(each[0].size),
                    "tokens": self.format_size_human_readable(
                        each[0].note.get("tokens", "-"), suffix=""
                    ),
                    "loader": each[0].note.get("loader", "-"),
                    "date_created": each[0].date_created.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for each in session.execute(statement).all()
            ]

        if results:
            file_list = pd.DataFrame.from_records(results)
        else:
            file_list = pd.DataFrame.from_records(
                [
                    {
                        "id": "-",
                        "name": "-",
                        "size": "-",
                        "tokens": "-",
                        "loader": "-",
                        "date_created": "-",
                    }
                ]
            )

        return results, file_list

    def list_file_names(self, file_list_state):
        if file_list_state:
            file_names = [(item["name"], item["id"]) for item in file_list_state]
        else:
            file_names = []

        return gr.update(choices=file_names)

    def list_group(self, user_id, file_list):
        file_id_to_name = {item["id"]: item["name"] for item in file_list} if file_list else {}

        if user_id is None:
            return [], pd.DataFrame.from_records(
                [
                    {
                        "id": "-",
                        "name": "-",
                        "files": "-",
                        "date_created": "-",
                    }
                ]
            )

        FileGroup = self._index._resources["FileGroup"]
        with Session(engine) as session:
            statement = select(FileGroup)
            if self._index.config.get("private", False):
                statement = statement.where(FileGroup.user == user_id)

            results = [
                {
                    "id": each[0].id,
                    "name": each[0].name,
                    "files": each[0].data.get("files", []),
                    "date_created": each[0].date_created.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for each in session.execute(statement).all()
            ]

        if results:
            formatted_results = deepcopy(results)
            for item in formatted_results:
                file_names = [
                    file_id_to_name.get(file_id, "-") for file_id in item["files"]
                ]
                item["files"] = ", ".join(
                    f"'{it[:MAX_FILENAME_LENGTH]}..'" if len(it) > MAX_FILENAME_LENGTH else f"'{it}'"
                    for it in file_names
                )
                item_count = len(file_names)
                item_postfix = "s" if item_count > 1 else ""
                item["files"] = f"[{item_count} item{item_postfix}] " + item["files"]

            group_list = pd.DataFrame.from_records(formatted_results)
        else:
            group_list = pd.DataFrame.from_records(
                [
                    {
                        "id": "-",
                        "name": "-",
                        "files": "-",
                        "date_created": "-",
                    }
                ]
            )

        return results, group_list

    def set_group_id_selector(self, selected_group_id):
        FileGroup = self._index._resources["FileGroup"]
        with Session(engine) as session:
            current_group = (
                session.query(FileGroup).filter_by(id=selected_group_id).first()
            )

        file_ids = [json.dumps(current_group.data["files"])]
        return [file_ids, "select", gr.Tabs(selected="chat-tab")]

    def save_group(self, group_id, group_name, group_files, user_id):
        FileGroup = self._index._resources["FileGroup"]

        with Session(engine) as session:
            if group_id:
                current_group = session.query(FileGroup).filter_by(id=group_id).first()
                current_group.name = group_name
                current_group.data["files"] = group_files
                session.commit()
            else:
                current_group = (
                    session.query(FileGroup)
                    .filter_by(name=group_name, user=user_id)
                    .first()
                )
                if current_group:
                    raise gr.Error(f"Group {group_name} already exists")

                current_group = FileGroup(
                    name=group_name,
                    data={"files": group_files},  # type: ignore
                    user=user_id,
                )
                session.add(current_group)
                session.commit()

            group_id = current_group.id

        gr.Info(f"Group {group_name} has been saved")
        return group_id

    def delete_group(self, group_id):
        if not group_id:
            raise gr.Error("No group is selected")

        FileGroup = self._index._resources["FileGroup"]
        with Session(engine) as session:
            group = session.execute(
                select(FileGroup).where(FileGroup.id == group_id)
            ).first()
            if group:
                item = group[0]
                group_name = item.name
                session.delete(item)
                session.commit()
                gr.Info(f"Group {group_name} has been deleted")
            else:
                raise gr.Error("No group found")

        return None

    def interact_file_list(self, list_files, ev: gr.SelectData):
        if ev.value == "-" and ev.index[0] == 0:
            gr.Info("No file is uploaded")
            return None, self.selected_panel_false

        if not ev.selected:
            return None, self.selected_panel_false

        return list_files["id"][ev.index[0]], self.selected_panel_true.format(
            name=list_files["name"][ev.index[0]]
        )

    def interact_group_list(self, list_groups, ev: gr.SelectData):
        selected_id = ev.index[0]
        if (not ev.value or ev.value == "-") and selected_id == 0:
            raise gr.Error("No group is selected")

        selected_item = list_groups[selected_id]
        selected_group_id = selected_item["id"]
        return (
            "### Group Information",
            selected_group_id,
            selected_item["name"],
            selected_item["files"],
        )
