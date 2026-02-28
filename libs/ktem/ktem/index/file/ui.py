"""Compatibility shim for file index UI.

Deprecated module path for implementation details:
- use `ktem.index.file.file_ui` for new code.
"""

from .file_ui import DirectoryUpload, File, FileIndexPage, FileSelector

__all__ = [
    "DirectoryUpload",
    "File",
    "FileIndexPage",
    "FileSelector",
]
