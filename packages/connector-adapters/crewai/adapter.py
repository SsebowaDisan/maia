"""ACP adapter for CrewAI — wraps a CrewAI Crew to emit ACP events.

Usage:
    from crewai import Agent, Task, Crew
    from maia_acp.adapters.crewai import ACPCrewAIAdapter

    researcher = Agent(role="Researcher", ...)
    analyst = Agent(role="Analyst", ...)
    crew = Crew(agents=[researcher, analyst], tasks=[...])

    acp_crew = ACPCrewAIAdapter(crew=crew, run_id="run_123")

    for event in acp_crew.run():
        print(event.model_dump_json())
"""

from __future__ import annotations

import time
from typing import Any, Generator

from maia_acp import ACPEvent, envelope, message, activity, capabilities, handoff


class ACPCrewAIAdapter:
    """Wraps a CrewAI Crew to emit ACP events during execution."""

    def __init__(
        self,
        crew: Any,
        run_id: str = "",
    ) -> None:
        self.crew = crew
        self.run_id = run_id or f"run_{int(time.time())}"

    def _agent_id(self, agent: Any) -> str:
        role = getattr(agent, "role", "agent").lower().replace(" ", "_")
        return f"agent://{role}"

    def _agent_caps(self, agent: Any) -> ACPEvent:
        agent_id = self._agent_id(agent)
        role = getattr(agent, "role", "agent")
        goal = getattr(agent, "goal", "")
        backstory = getattr(agent, "backstory", "")

        tools = []
        for tool in getattr(agent, "tools", []):
            tool_name = getattr(tool, "name", str(tool))
            tools.append({
                "skill_id": tool_name,
                "description": getattr(tool, "description", tool_name),
            })

        return envelope(
            agent_id,
            self.run_id,
            "capabilities",
            capabilities(
                agent_id=agent_id,
                name=role,
                description=goal,
                role=role.lower(),
                skills=tools or [{"skill_id": "crewai_agent", "description": goal}],
            ),
        )

    def run(self) -> Generator[ACPEvent, None, None]:
        """Run the crew and yield ACP events.

        Emits:
        - capabilities for each agent
        - handoff events between tasks
        - activity events during execution
        - message events with results
        """
        agents = getattr(self.crew, "agents", [])
        tasks = getattr(self.crew, "tasks", [])

        # Emit capabilities for all agents
        for agent in agents:
            yield self._agent_caps(agent)

        # Run tasks and emit events
        for i, task in enumerate(tasks):
            task_agent = getattr(task, "agent", None)
            agent_id = self._agent_id(task_agent) if task_agent else "agent://unknown"
            task_desc = getattr(task, "description", f"Task {i + 1}")

            # Handoff from previous task
            if i > 0:
                prev_task = tasks[i - 1]
                prev_agent = getattr(prev_task, "agent", None)
                prev_id = self._agent_id(prev_agent) if prev_agent else "agent://unknown"
                yield envelope(
                    prev_id,
                    self.run_id,
                    "handoff",
                    handoff(
                        from_agent=prev_id,
                        to=agent_id,
                        description=task_desc[:200],
                    ),
                )

            # Activity: thinking
            yield envelope(
                agent_id,
                self.run_id,
                "event",
                activity(
                    agent_id=agent_id,
                    activity_type="thinking",
                    detail=f"Working on: {task_desc[:100]}",
                ),
            )

        # Execute the crew
        try:
            result = self.crew.kickoff()
            result_text = str(result) if result else "Crew completed"

            # Final message from last agent
            last_agent = agents[-1] if agents else None
            last_id = self._agent_id(last_agent) if last_agent else "agent://crew"

            yield envelope(
                last_id,
                self.run_id,
                "message",
                message(
                    from_agent=last_id,
                    to="agent://brain",
                    intent="summarize",
                    content=result_text,
                    mood="confident",
                ),
            )

        except Exception as exc:
            yield envelope(
                "agent://crew",
                self.run_id,
                "event",
                activity(
                    agent_id="agent://crew",
                    activity_type="error",
                    detail=str(exc)[:300],
                ),
            )
