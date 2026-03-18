"""Agent-facing filesystem tools — read, write, edit, grep, ls."""
from __future__ import annotations

import json
import logging
from typing import Any, Generator

from .backend import FilesystemBackend, LocalFilesystemBackend

logger = logging.getLogger(__name__)

# Each tool follows the Maia agent tool pattern:
#   - name, description, parameters (JSON Schema)
#   - execute(params) -> Generator[dict, None, None] yielding trace events


def _get_backend(settings: dict[str, Any]) -> FilesystemBackend:
    root = settings.get("workspace_root", ".")
    return LocalFilesystemBackend(root)


class FileReadTool:
    name = "file_read"
    description = "Read a file from the agent workspace. Returns numbered lines."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the file"},
            "offset": {"type": "integer", "description": "Line offset (0-based)", "default": 0},
            "limit": {"type": "integer", "description": "Max lines to return", "default": 200},
        },
        "required": ["path"],
    }

    def execute(self, params: dict[str, Any], settings: dict[str, Any]) -> Generator[dict, None, None]:
        backend = _get_backend(settings)
        try:
            content = backend.read(
                params["path"],
                offset=params.get("offset", 0),
                limit=params.get("limit", 200),
            )
            yield {"type": "result", "content": content}
        except (FileNotFoundError, PermissionError) as exc:
            yield {"type": "error", "content": str(exc)}


class FileWriteTool:
    name = "file_write"
    description = "Write content to a file in the agent workspace. Creates parent directories."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the file"},
            "content": {"type": "string", "description": "File content to write"},
        },
        "required": ["path", "content"],
    }

    def execute(self, params: dict[str, Any], settings: dict[str, Any]) -> Generator[dict, None, None]:
        backend = _get_backend(settings)
        try:
            backend.write(params["path"], params["content"])
            yield {"type": "result", "content": f"Wrote {len(params['content'])} bytes to {params['path']}"}
        except PermissionError as exc:
            yield {"type": "error", "content": str(exc)}


class FileEditTool:
    name = "file_edit"
    description = "Replace exact text in a file. The old_text must appear exactly once."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the file"},
            "old_text": {"type": "string", "description": "Exact text to find"},
            "new_text": {"type": "string", "description": "Replacement text"},
        },
        "required": ["path", "old_text", "new_text"],
    }

    def execute(self, params: dict[str, Any], settings: dict[str, Any]) -> Generator[dict, None, None]:
        backend = _get_backend(settings)
        try:
            ok = backend.edit(params["path"], params["old_text"], params["new_text"])
            if ok:
                yield {"type": "result", "content": f"Edited {params['path']} successfully."}
            else:
                yield {"type": "error", "content": "old_text not found in file."}
        except (FileNotFoundError, PermissionError, ValueError) as exc:
            yield {"type": "error", "content": str(exc)}


class FileSearchTool:
    name = "file_search"
    description = "Search file contents in the workspace using a regex pattern."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
            "glob": {"type": "string", "description": "File glob filter", "default": "*"},
        },
        "required": ["pattern"],
    }

    def execute(self, params: dict[str, Any], settings: dict[str, Any]) -> Generator[dict, None, None]:
        backend = _get_backend(settings)
        try:
            matches = backend.search(
                params["pattern"],
                path=params.get("path", "."),
                glob=params.get("glob", "*"),
            )
            if not matches:
                yield {"type": "result", "content": "No matches found."}
                return
            lines = [f"{m.path}:{m.line_number}: {m.line_text}" for m in matches]
            yield {"type": "result", "content": f"Found {len(matches)} matches:\n" + "\n".join(lines)}
        except (NotADirectoryError, PermissionError) as exc:
            yield {"type": "error", "content": str(exc)}


class FileListTool:
    name = "file_list"
    description = "List files and directories in the agent workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path", "default": "."},
        },
    }

    def execute(self, params: dict[str, Any], settings: dict[str, Any]) -> Generator[dict, None, None]:
        backend = _get_backend(settings)
        try:
            entries = backend.list_dir(params.get("path", "."))
            if not entries:
                yield {"type": "result", "content": "Empty directory."}
                return
            lines = []
            for e in entries:
                if e.is_dir:
                    lines.append(f"  {e.path}/")
                else:
                    size_kb = e.size / 1024
                    lines.append(f"  {e.path}  ({size_kb:.1f} KB)")
            yield {"type": "result", "content": "\n".join(lines)}
        except (NotADirectoryError, PermissionError) as exc:
            yield {"type": "error", "content": str(exc)}


FILESYSTEM_TOOLS = [FileReadTool, FileWriteTool, FileEditTool, FileSearchTool, FileListTool]
