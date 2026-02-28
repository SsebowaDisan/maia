from ktem.app import BasePage

from .constants import KH_DEMO_MODE
from .file_index_actions import FileIndexActionsMixin
from .file_index_data import FileIndexDataMixin
from .file_index_events import FileIndexEventMixin
from .file_index_indexing import FileIndexIndexingMixin
from .file_index_render import FileIndexRenderMixin


class FileIndexPage(
    BasePage,
    FileIndexRenderMixin,
    FileIndexActionsMixin,
    FileIndexEventMixin,
    FileIndexIndexingMixin,
    FileIndexDataMixin,
):
    def __init__(self, app, index):
        super().__init__(app)
        self._index = index
        self._supported_file_types_str = self._index.config.get(
            "supported_file_types", ""
        )
        self._supported_file_types = [
            each.strip() for each in self._supported_file_types_str.split(",")
        ]
        self.selected_panel_false = "Selected file: (please select above)"
        self.selected_panel_true = "Selected file: {name}"
        self.public_events = [f"onFileIndex{index.id}Changed"]

        if not KH_DEMO_MODE:
            self.on_building_ui()
