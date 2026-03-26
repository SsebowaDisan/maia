"""ACP adapter for AutoGen — wraps AutoGen group chats to emit ACP events.

Usage:
    from autogen import AssistantAgent, UserProxyAgent, GroupChat
    from maia_acp.adapters.autogen import ACPAutoGenAdapter

    researcher = AssistantAgent(name="researcher", ...)
    analyst = AssistantAgent(name="analyst", ...)
    group_chat = GroupChat(agents=[researcher, analyst], ...)

    acp_adapter = ACPAutoGenAdapter(group_chat=group_chat, run_id="run_123")

    for event in acp_adapter.run("Analyze Q4 revenue"):
        print(event.model_dump_json())
"""

from __future__ import annotations

import time
from typing import Any, Generator

from maia_acp import ACPEvent, envelope, message, activity, capabilities


class ACPAutoGenAdapter:
    """Wraps an AutoGen GroupChat to emit ACP events."""

    def __init__(
        self,
        group_chat: Any,
        run_id: str = "",
    ) -> None:
        self.group_chat = group_chat
        self.run_id = run_id or f"run_{int(time.time())}"

    def _agent_id(self, agent: Any) -> str:
        name = getattr(agent, "name", "agent").lower().replace(" ", "_")
        return f"agent://{name}"

    def _agent_caps(self, agent: Any) -> ACPEvent:
        agent_id = self._agent_id(agent)
        name = getattr(agent, "name", "agent")
        system_msg = getattr(agent, "system_message", "")

        return envelope(
            agent_id,
            self.run_id,
            "capabilities",
            capabilities(
                agent_id=agent_id,
                name=name,
                description=system_msg[:200] if system_msg else name,
                role=name.lower(),
                skills=[{"skill_id": "autogen_agent", "description": f"AutoGen {name}"}],
            ),
        )

    def run(self, query: str = "") -> Generator[ACPEvent, None, None]:
        """Run the group chat and yield ACP events.

        Hooks into AutoGen's message callback to emit ACP events
        for each agent turn.
        """
        agents = getattr(self.group_chat, "agents", [])

        # Emit capabilities
        for agent in agents:
            yield self._agent_caps(agent)

        # Collect events via callback
        collected_events: list[ACPEvent] = []

        original_send = None

        # Try to hook into the message flow
        def _capture_message(sender: Any, msg: Any, *args: Any, **kwargs: Any) -> None:
            agent_id = self._agent_id(sender)
            content = str(msg) if isinstance(msg, str) else msg.get("content", str(msg))

            collected_events.append(
                envelope(
                    agent_id,
                    self.run_id,
                    "message",
                    message(
                        from_agent=agent_id,
                        to="agent://broadcast",
                        intent="propose",
                        content=content,
                    ),
                )
            )

        # Run the group chat
        try:
            # AutoGen v0.4+ uses ChatResult
            if hasattr(self.group_chat, "initiate_chat"):
                # Hook into agents' send methods
                for agent in agents:
                    if hasattr(agent, "register_hook"):
                        agent.register_hook("process_last_received_message", _capture_message)

                result = self.group_chat.initiate_chat(
                    agents[0] if agents else None,
                    message=query,
                )

                # Yield collected events
                yield from collected_events

                # Final summary
                result_text = str(result) if result else "Group chat completed"
                yield envelope(
                    "agent://group_chat",
                    self.run_id,
                    "message",
                    message(
                        from_agent="agent://group_chat",
                        to="agent://brain",
                        intent="summarize",
                        content=result_text,
                        mood="confident",
                    ),
                )

            else:
                # Fallback: run without hooks
                yield envelope(
                    "agent://group_chat",
                    self.run_id,
                    "event",
                    activity(
                        agent_id="agent://group_chat",
                        activity_type="thinking",
                        detail=f"Processing: {query[:100]}",
                    ),
                )

        except Exception as exc:
            yield envelope(
                "agent://group_chat",
                self.run_id,
                "event",
                activity(
                    agent_id="agent://group_chat",
                    activity_type="error",
                    detail=str(exc)[:300],
                ),
            )
