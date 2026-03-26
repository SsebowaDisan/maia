"""ACP adapter for LangChain — wraps any LangChain agent to emit ACP events.

Usage:
    from langchain.agents import create_react_agent
    from maia_acp.adapters.langchain import ACPLangChainAdapter

    agent = create_react_agent(llm, tools, prompt)
    acp_agent = ACPLangChainAdapter(
        agent=agent,
        agent_id="agent://researcher",
        name="Researcher",
        role="research",
    )

    # Run and get ACP events
    for event in acp_agent.run("Find Q4 revenue data"):
        print(event.model_dump_json())
"""

from __future__ import annotations

import time
from typing import Any, Generator

from maia_acp import ACPEvent, envelope, message, activity, artifact, capabilities


class ACPLangChainAdapter:
    """Wraps a LangChain agent to emit ACP events during execution."""

    def __init__(
        self,
        agent: Any,
        agent_id: str,
        name: str,
        role: str = "agent",
        run_id: str = "",
        personality: dict[str, Any] | None = None,
        skills: list[dict[str, Any]] | None = None,
    ) -> None:
        self.agent = agent
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.run_id = run_id or f"run_{int(time.time())}"
        self.personality = personality
        self.skills = skills or []

    def get_capabilities(self) -> ACPEvent:
        """Return an ACP capabilities event describing this agent."""
        return envelope(
            self.agent_id,
            self.run_id,
            "capabilities",
            capabilities(
                agent_id=self.agent_id,
                name=self.name,
                role=self.role,
                personality=self.personality,
                skills=self.skills or [
                    {"skill_id": "langchain_agent", "description": "LangChain ReAct agent"}
                ],
            ),
        )

    def run(
        self,
        query: str,
        *,
        to_agent: str = "agent://brain",
    ) -> Generator[ACPEvent, None, None]:
        """Run the agent and yield ACP events.

        Emits:
        - capabilities (once)
        - activity events (thinking, tool_calling)
        - message with final result
        """
        yield self.get_capabilities()

        # Emit thinking
        yield envelope(
            self.agent_id,
            self.run_id,
            "event",
            activity(
                agent_id=self.agent_id,
                activity_type="thinking",
                detail=f"Processing: {query[:100]}",
            ),
        )

        try:
            # Use streaming if available, otherwise invoke
            if hasattr(self.agent, "stream"):
                result_text = ""
                for chunk in self.agent.stream({"input": query}):
                    # Emit intermediate steps as activity events
                    if isinstance(chunk, dict):
                        if "intermediate_steps" in chunk:
                            for step in chunk["intermediate_steps"]:
                                action = step[0] if isinstance(step, tuple) else step
                                tool_name = getattr(action, "tool", "unknown")
                                tool_input = str(getattr(action, "tool_input", ""))[:200]

                                yield envelope(
                                    self.agent_id,
                                    self.run_id,
                                    "event",
                                    activity(
                                        agent_id=self.agent_id,
                                        activity_type="tool_calling",
                                        detail=f"Using {tool_name}",
                                        tool={
                                            "tool_id": tool_name,
                                            "tool_name": tool_name,
                                            "input_summary": tool_input,
                                            "status": "running",
                                        },
                                    ),
                                )

                        if "output" in chunk:
                            result_text = chunk["output"]
            else:
                result = self.agent.invoke({"input": query})
                result_text = result.get("output", str(result)) if isinstance(result, dict) else str(result)

            # Emit final message
            yield envelope(
                self.agent_id,
                self.run_id,
                "message",
                message(
                    from_agent=self.agent_id,
                    to=to_agent,
                    intent="propose",
                    content=result_text,
                    mood="confident",
                ),
            )

        except Exception as exc:
            yield envelope(
                self.agent_id,
                self.run_id,
                "event",
                activity(
                    agent_id=self.agent_id,
                    activity_type="error",
                    detail=str(exc)[:300],
                ),
            )
