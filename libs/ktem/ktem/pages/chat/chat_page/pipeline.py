import asyncio
import json
import re
from copy import deepcopy
from typing import Optional

import gradio as gr
from ktem.components import reasonings
from ktem.reasoning.prompt_optimization.suggest_conversation_name import (
    SuggestConvNamePipeline,
)
from ktem.reasoning.prompt_optimization.suggest_followup_chat import (
    SuggestFollowupQuesPipeline,
)
from maia.base import Document
from maia.indices.qa.utils import strip_think_tag
from theflow.settings import settings as flowsettings

from ....utils import SUPPORTED_LANGUAGE_MAP
from ....utils.commands import WEB_SEARCH_COMMAND
from ..chat_suggestion import ChatSuggestion
from .constants import DEFAULT_SETTING, WebSearch


class ChatPagePipelineMixin:
    def create_pipeline(
        self,
        settings: dict,
        session_reasoning_type: str,
        session_llm: str,
        session_use_mindmap: bool | str,
        session_use_citation: str,
        session_language: str,
        state: dict,
        command_state: str | None,
        user_id: int,
        session_mindmap_max_depth: int | str | None = None,
        session_include_reasoning_map: bool | str | None = None,
        *selecteds,
    ):
        print(
            "Session reasoning type",
            session_reasoning_type,
            "use mindmap",
            session_use_mindmap,
            "use citation",
            session_use_citation,
            "language",
            session_language,
        )
        print("Session LLM", session_llm)
        reasoning_mode = (
            settings["reasoning.use"]
            if session_reasoning_type in (DEFAULT_SETTING, None)
            else session_reasoning_type
        )
        reasoning_cls = reasonings[reasoning_mode]
        print("Reasoning class", reasoning_cls)
        reasoning_id = reasoning_cls.get_info()["id"]

        settings = deepcopy(settings)
        llm_setting_key = f"reasoning.options.{reasoning_id}.llm"
        if llm_setting_key in settings and session_llm not in (
            DEFAULT_SETTING,
            None,
            "",
        ):
            settings[llm_setting_key] = session_llm

        if session_use_mindmap not in (DEFAULT_SETTING, None):
            settings["reasoning.options.simple.create_mindmap"] = session_use_mindmap
        if session_mindmap_max_depth not in (DEFAULT_SETTING, None, ""):
            try:
                parsed_depth = int(session_mindmap_max_depth)
            except Exception:
                parsed_depth = 4
            settings["reasoning.options.simple.mindmap_max_depth"] = max(
                2, min(8, parsed_depth)
            )
        if session_include_reasoning_map not in (DEFAULT_SETTING, None, ""):
            settings["reasoning.options.simple.include_reasoning_map"] = bool(
                session_include_reasoning_map
            )

        if session_use_citation not in (DEFAULT_SETTING, None):
            settings[
                "reasoning.options.simple.highlight_citation"
            ] = session_use_citation

        if session_language not in (DEFAULT_SETTING, None):
            settings["reasoning.lang"] = session_language

        retrievers = []

        if command_state == WEB_SEARCH_COMMAND:
            if not WebSearch:
                raise ValueError("Web search back-end is not available.")

            web_search = WebSearch()
            retrievers.append(web_search)
        else:
            for index in self._app.index_manager.indices:
                index_selected = []
                if isinstance(index.selector, int):
                    index_selected = selecteds[index.selector]
                if isinstance(index.selector, tuple):
                    for i in index.selector:
                        index_selected.append(selecteds[i])
                iretrievers = index.get_retriever_pipelines(
                    settings, user_id, index_selected
                )
                retrievers += iretrievers

        reasoning_state = {
            "app": deepcopy(state["app"]),
            "pipeline": deepcopy(state.get(reasoning_id, {})),
        }

        pipeline = reasoning_cls.get_pipeline(settings, reasoning_state, retrievers)

        return pipeline, reasoning_state

    def chat_fn(
        self,
        conversation_id,
        chat_history,
        settings,
        reasoning_type,
        llm_type,
        use_mind_map,
        use_citation,
        language,
        chat_state,
        command_state,
        user_id,
        mindmap_max_depth=None,
        include_reasoning_map=None,
        *selecteds,
    ):
        chat_input, chat_output = chat_history[-1]
        chat_history = chat_history[:-1]

        if chat_output:
            chat_state["app"]["regen"] = True

        queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()

        pipeline, reasoning_state = self.create_pipeline(
            settings,
            reasoning_type,
            llm_type,
            use_mind_map,
            use_citation,
            language,
            chat_state,
            command_state,
            user_id,
            mindmap_max_depth,
            include_reasoning_map,
            *selecteds,
        )
        print("Reasoning state", reasoning_state)
        pipeline.set_output_queue(queue)

        text, refs, plot, plot_gr = "", "", None, gr.update(visible=False)
        msg_placeholder = getattr(
            flowsettings, "KH_CHAT_MSG_PLACEHOLDER", "Thinking ..."
        )
        print(msg_placeholder)
        yield (
            chat_history + [(chat_input, text or msg_placeholder)],
            refs,
            plot_gr,
            plot,
            chat_state,
        )

        try:
            for response in pipeline.stream(chat_input, conversation_id, chat_history):
                if not isinstance(response, Document):
                    continue

                if response.channel is None:
                    continue

                if response.channel == "chat":
                    if response.content is None:
                        text = ""
                    else:
                        text += response.content

                if response.channel == "info":
                    if response.content is None:
                        refs = ""
                    else:
                        refs += response.content

                if response.channel == "plot":
                    plot = response.content
                    plot_gr = self._json_to_plot(plot)

                chat_state[pipeline.get_info()["id"]] = reasoning_state["pipeline"]

                yield (
                    chat_history + [(chat_input, text or msg_placeholder)],
                    refs,
                    plot_gr,
                    plot,
                    chat_state,
                )
        except ValueError as exc:
            print(exc)

        if not text:
            empty_msg = getattr(
                flowsettings, "KH_CHAT_EMPTY_MSG_PLACEHOLDER", "(Sorry, I don't know)"
            )
            print(f"Generate nothing: {empty_msg}")
            yield (
                chat_history + [(chat_input, text or empty_msg)],
                refs,
                plot_gr,
                plot,
                chat_state,
            )

    def check_and_suggest_name_conv(self, chat_history):
        suggest_pipeline = SuggestConvNamePipeline()
        new_name = gr.update()
        renamed = False

        if len(chat_history) == 1:
            suggested_name = suggest_pipeline(chat_history).text
            suggested_name = strip_think_tag(suggested_name)
            suggested_name = suggested_name.replace('"', "").replace("'", "")[:40]
            new_name = gr.update(value=suggested_name)
            renamed = True

        return new_name, renamed

    def suggest_chat_conv(
        self,
        settings,
        session_language,
        chat_history,
        use_suggestion,
    ):
        target_language = (
            session_language
            if session_language not in (DEFAULT_SETTING, None)
            else settings["reasoning.lang"]
        )
        if use_suggestion:
            suggest_pipeline = SuggestFollowupQuesPipeline()
            suggest_pipeline.lang = SUPPORTED_LANGUAGE_MAP.get(
                target_language, "English"
            )
            suggested_questions = [[each] for each in ChatSuggestion.CHAT_SAMPLES]

            if len(chat_history) >= 1:
                suggested_resp = suggest_pipeline(chat_history).text
                if ques_res := re.search(
                    r"\[(.*?)\]", re.sub("\n", "", suggested_resp)
                ):
                    ques_res_str = ques_res.group()
                    try:
                        suggested_questions = json.loads(ques_res_str)
                        suggested_questions = [[x] for x in suggested_questions]
                    except Exception:
                        pass

            return gr.update(visible=True), suggested_questions

        return gr.update(visible=False), gr.update()
