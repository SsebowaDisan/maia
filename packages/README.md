# Maia SDK — Packages

> The collaboration and observability layer for AI agents.

## Packages

| Package | Description | Language |
|---------|-------------|----------|
| [`acp-spec`](./acp-spec/) | ACP v1 JSON Schema definitions | JSON Schema |
| [`acp-js`](./acp-js/) | `@maia/acp` — TypeScript/JS client | TypeScript |
| [`acp-py`](./acp-py/) | `maia-acp` — Python client | Python |
| [`theatre-react`](./theatre-react/) | `@maia/theatre` — React visualization SDK | React/TypeScript |
| [`connector-adapters`](./connector-adapters/) | Framework adapters (LangChain, CrewAI, AutoGen) | Python |

## Quick Start

### Watch agents collaborate (React)

```tsx
import { Theatre } from '@maia/theatre';

// Live mode — connect to any SSE stream
<Theatre streamUrl="/acp/events" />

// Replay mode — feed recorded events
<Theatre recordedEvents={events} />
```

### Emit ACP events (Python)

```python
from maia_acp import ACPClient, message

client = ACPClient(agent_id="agent://researcher")

# Create a message
msg = message(
    from_agent="agent://researcher",
    to="agent://analyst",
    intent="challenge",
    content="The 34% growth figure needs verification."
)

# Wrap in an event envelope
event = client.emit_message(msg)
```

### Adapt existing frameworks

```python
# LangChain
from maia_acp.adapters.langchain import ACPLangChainAdapter
acp_agent = ACPLangChainAdapter(agent=my_langchain_agent, agent_id="agent://researcher")

# CrewAI
from maia_acp.adapters.crewai import ACPCrewAIAdapter
acp_crew = ACPCrewAIAdapter(crew=my_crew)

# AutoGen
from maia_acp.adapters.autogen import ACPAutoGenAdapter
acp_chat = ACPAutoGenAdapter(group_chat=my_group_chat)
```

## Architecture

```
MCP  ──→  Tools        (Anthropic — how agents use tools)
ACP  ──→  Agents       (Maia — how agents talk to each other)
AG-UI ──→  UI          (CopilotKit — how agents stream to frontends)

Theatre renders ACP events as a live visualization.
```

## License

MIT
