import os
import shutil
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Generator

import gradio as gr
from ktem.db.engine import engine
from sqlalchemy.orm import Session
from theflow.settings import settings as flowsettings

from ....utils.rate_limit import check_rate_limit
from ..utils import download_arxiv_pdf, is_arxiv_url
from .constants import KH_DEMO_MODE


class FileIndexIndexingMixin:
    def _may_extract_zip(self, files, zip_dir: str):
        zip_files = [file for file in files if file.endswith(".zip")]
        remaining_files = [file for file in files if not file.endswith("zip")]
        errors: list[str] = []

        shutil.rmtree(zip_dir, ignore_errors=True)

        for zip_file in zip_files:
            basename = os.path.splitext(os.path.basename(zip_file))[0]
            zip_out_dir = os.path.join(zip_dir, basename)
            os.makedirs(zip_out_dir, exist_ok=True)
            with zipfile.ZipFile(zip_file, "r") as zip_ref:
                zip_ref.extractall(zip_out_dir)

        n_zip_file = 0
        for root, dirs, files in os.walk(zip_dir):
            for file in files:
                ext = os.path.splitext(file)[1]
                if ext not in [".zip"] and ext in self._supported_file_types:
                    remaining_files += [os.path.join(root, file)]
                    n_zip_file += 1

        if n_zip_file > 0:
            print(f"Update zip files: {n_zip_file}")

        return remaining_files, errors

    def index_fn(
        self, files, urls, reindex: bool, settings, user_id
    ) -> Generator[tuple[str, str], None, None]:
        if urls:
            files = [it.strip() for it in urls.split("\n")]
            errors = self.validate_urls(files)
        else:
            if not files:
                gr.Info("No uploaded file")
                yield "", ""
                return
            files, unzip_errors = self._may_extract_zip(
                files, flowsettings.KH_ZIP_INPUT_DIR
            )
            errors = self.validate_files(files)
            errors.extend(unzip_errors)

        if errors:
            gr.Warning(", ".join(errors))
            yield "", ""
            return

        gr.Info(f"Start indexing {len(files)} files...")
        indexing_pipeline = self._index.get_indexing_pipeline(settings, user_id)

        outputs, debugs = [], []
        output_stream = indexing_pipeline.stream(files, reindex=reindex)
        try:
            while True:
                response = next(output_stream)
                if response is None:
                    continue
                if response.channel == "index":
                    if response.content["status"] == "success":
                        outputs.append(f"\u2705 | {response.content['file_name']}")
                    elif response.content["status"] == "failed":
                        outputs.append(
                            f"\u274c | {response.content['file_name']}: "
                            f"{response.content['message']}"
                        )
                elif response.channel == "debug":
                    debugs.append(response.text)
                yield "\n".join(outputs), "\n".join(debugs)
        except StopIteration as stop:
            results, index_errors, docs = stop.value
        except Exception as exc:
            debugs.append(f"Error: {exc}")
            yield "\n".join(outputs), "\n".join(debugs)
            return

        n_successes = len([_ for _ in results if _])
        if n_successes:
            gr.Info(f"Successfully index {n_successes} files")
        n_errors = len([_ for _ in errors if _])
        if n_errors:
            gr.Warning(f"Have errors for {n_errors} files")

        return results

    def index_fn_file_with_default_loaders(
        self, files, reindex: bool, settings, user_id
    ) -> list["str"]:
        print("Overriding with default loaders")
        exist_ids = []
        to_process_files = []
        for str_file_path in files:
            file_path = Path(str(str_file_path))
            exist_id = (
                self._index.get_indexing_pipeline(settings, user_id)
                .route(file_path)
                .get_id_if_exists(file_path)
            )
            if exist_id:
                exist_ids.append(exist_id)
            else:
                to_process_files.append(str_file_path)

        returned_ids = []
        settings = deepcopy(settings)
        settings[f"index.options.{self._index.id}.reader_mode"] = "default"
        settings[f"index.options.{self._index.id}.quick_index_mode"] = True
        if to_process_files:
            _iter = self.index_fn(to_process_files, [], reindex, settings, user_id)
            try:
                while next(_iter):
                    pass
            except StopIteration as stop:
                returned_ids = stop.value

        return exist_ids + returned_ids

    def index_fn_url_with_default_loaders(
        self,
        urls,
        reindex: bool,
        settings,
        user_id,
        request: gr.Request,
    ):
        if KH_DEMO_MODE:
            check_rate_limit("file_upload", request)

        returned_ids: list[str] = []
        settings = deepcopy(settings)
        settings[f"index.options.{self._index.id}.reader_mode"] = "default"
        settings[f"index.options.{self._index.id}.quick_index_mode"] = True

        if KH_DEMO_MODE:
            urls_splitted = urls.split("\n")
            if not all(is_arxiv_url(url) for url in urls_splitted):
                raise ValueError("All URLs must be valid arXiv URLs")

            output_files = [
                download_arxiv_pdf(
                    url,
                    output_path=os.environ.get("GRADIO_TEMP_DIR", "/tmp"),
                )
                for url in urls_splitted
            ]

            exist_ids = []
            to_process_files = []
            for str_file_path in output_files:
                file_path = Path(str_file_path)
                exist_id = (
                    self._index.get_indexing_pipeline(settings, user_id)
                    .route(file_path)
                    .get_id_if_exists(file_path)
                )
                if exist_id:
                    exist_ids.append(exist_id)
                else:
                    to_process_files.append(str_file_path)

            returned_ids = []
            if to_process_files:
                _iter = self.index_fn(to_process_files, [], reindex, settings, user_id)
                try:
                    while next(_iter):
                        pass
                except StopIteration as stop:
                    returned_ids = stop.value

            returned_ids = exist_ids + returned_ids
        else:
            if urls:
                _iter = self.index_fn([], urls, reindex, settings, user_id)
                try:
                    while next(_iter):
                        pass
                except StopIteration as stop:
                    returned_ids = stop.value

        return returned_ids

    def index_files_from_dir(
        self, folder_path, reindex, settings, user_id
    ) -> Generator[tuple[str, str], None, None]:
        if not folder_path:
            yield "", ""
            return

        import fnmatch

        include_patterns: list[str] = []
        exclude_patterns: list[str] = ["*.png", "*.gif", "*/.*"]
        if include_patterns and exclude_patterns:
            raise ValueError("Cannot have both include and exclude patterns")

        for idx in range(len(include_patterns)):
            if include_patterns[idx].startswith("*"):
                include_patterns[idx] = str(Path.cwd() / "**" / include_patterns[idx])
            else:
                include_patterns[idx] = str(
                    Path.cwd() / include_patterns[idx].strip("/")
                )

        for idx in range(len(exclude_patterns)):
            if exclude_patterns[idx].startswith("*"):
                exclude_patterns[idx] = str(Path.cwd() / "**" / exclude_patterns[idx])
            else:
                exclude_patterns[idx] = str(
                    Path.cwd() / exclude_patterns[idx].strip("/")
                )

        files: list[str] = [str(path) for path in Path(folder_path).glob("**/*.*")]
        if include_patterns:
            for pattern in include_patterns:
                files = fnmatch.filter(names=files, pat=pattern)

        if exclude_patterns:
            for pattern in exclude_patterns:
                files = [f for f in files if not fnmatch.fnmatch(name=f, pat=pattern)]

        yield from self.index_fn(files, [], reindex, settings, user_id)

    def validate_files(self, files: list[str]):
        paths = [Path(file) for file in files]
        errors = []
        if max_file_size := self._index.config.get("max_file_size", 0):
            errors_max_size = []
            for path in paths:
                if path.stat().st_size > max_file_size * 1e6:
                    errors_max_size.append(path.name)
            if errors_max_size:
                str_errors = ", ".join(errors_max_size)
                if len(str_errors) > 60:
                    str_errors = str_errors[:55] + "..."
                errors.append(
                    f"Maximum file size ({max_file_size} MB) exceeded: {str_errors}"
                )

        if max_number_of_files := self._index.config.get("max_number_of_files", 0):
            with Session(engine) as session:
                current_num_files = session.query(
                    self._index._resources["Source"].id
                ).count()
            if len(paths) + current_num_files > max_number_of_files:
                errors.append(
                    f"Maximum number of files ({max_number_of_files}) will be exceeded"
                )

        return errors

    def validate_urls(self, urls: list[str]):
        errors = []
        for url in urls:
            if not url.startswith("http") and not url.startswith("https"):
                errors.append(f"Invalid url `{url}`")
        return errors
