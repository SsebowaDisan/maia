import gradio as gr
from ktem.app import BasePage
from theflow.settings import settings as flowsettings

from .events import ChatPageEventsMixin
from .persistence import ChatPagePersistenceMixin
from .pipeline import ChatPagePipelineMixin
from .submission import ChatPageSubmissionMixin
from .ui import ChatPageUIMixin


class ChatPage(
    BasePage,
    ChatPageUIMixin,
    ChatPageEventsMixin,
    ChatPageSubmissionMixin,
    ChatPagePersistenceMixin,
    ChatPagePipelineMixin,
):
    def __init__(self, app):
        self._app = app
        self._indices_input = []

        self.on_building_ui()

        self._preview_links = gr.State(value=None)
        self._reasoning_type = gr.State(value=None)
        self._conversation_renamed = gr.State(value=False)
        self._use_suggestion = gr.State(
            value=getattr(flowsettings, "KH_FEATURE_CHAT_SUGGESTION", False)
        )
        self._info_panel_expanded = gr.State(value=True)
        self._command_state = gr.State(value=None)
        self._user_api_key = gr.Text(value="", visible=False)
