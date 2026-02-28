from __future__ import annotations

# Deprecated shim: moved to `api/services/upload/`.
from api.services.upload import (
    create_file_group,
    delete_file_group,
    delete_indexed_files,
    get_index,
    index_files,
    index_urls,
    list_file_groups,
    list_indexed_files,
    move_files_to_group,
    rename_file_group,
    resolve_indexed_file_path,
)

__all__ = [
    "get_index",
    "index_files",
    "index_urls",
    "list_indexed_files",
    "resolve_indexed_file_path",
    "list_file_groups",
    "create_file_group",
    "move_files_to_group",
    "rename_file_group",
    "delete_file_group",
    "delete_indexed_files",
]
