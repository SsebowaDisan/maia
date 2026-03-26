# ACP — Agent Collaboration Protocol

> The open protocol for AI agent-to-agent communication, collaboration, and observability.

## Why ACP?

| Layer | Protocol | What it solves |
|-------|----------|---------------|
| Tools | MCP (Anthropic) | Agents connect to tools |
| Agent-to-UI | AG-UI (CopilotKit) | Agents stream to frontends |
| **Agent-to-Agent** | **ACP (Maia)** | **Agents collaborate with each other** |

MCP is USB for tools. AG-UI is streaming to UI. **ACP is TCP/IP for agents.**

## Core Primitives

ACP v1 defines 6 primitives:

| Primitive | Purpose | Example |
|-----------|---------|---------|
| `message` | One agent talks to another | Researcher asks Analyst to verify data |
| `handoff` | Transfer task + context | Brain delegates "write report" to Writer |
| `review` | Evaluate another agent's output | Brain reviews Writer's draft |
| `artifact` | Pass work products | Analyst sends dataset to Writer |
| `event` | Stream live work activity | Agent emits "searching web..." |
| `capabilities` | Discover what an agent can do | Brain queries available agents |

## Event Format

Every ACP event follows this envelope:

```json
{
  "acp_version": "1.0",
  "run_id": "run_abc123",
  "agent_id": "agent://researcher",
  "event_type": "message",
  "timestamp": "2026-03-22T10:30:00Z",
  "payload": {}
}
```

## Message Format

```json
{
  "from": "agent://researcher",
  "to": "agent://analyst",
  "intent": "challenge",
  "content": "The 34% growth figure seems high. Can you verify against the original dataset?",
  "artifacts": [],
  "context": {
    "run_id": "run_abc123",
    "step": "data_verification",
    "thread_id": "thread_1"
  }
}
```

## Intents

Messages carry an `intent` that describes the communication purpose:

| Intent | Meaning |
|--------|---------|
| `propose` | Suggest an approach or idea |
| `challenge` | Question or push back on something |
| `clarify` | Ask for more information |
| `review` | Evaluate work and provide feedback |
| `handoff` | Transfer responsibility |
| `summarize` | Recap progress or decisions |
| `agree` | Confirm or approve |
| `escalate` | Flag for human intervention |

## Quick Start

### JavaScript/TypeScript
```bash
npm install @maia/acp
```

```typescript
import { ACPClient, message } from '@maia/acp';

const client = new ACPClient({ agentId: 'agent://my-agent' });

// Send a message to another agent
await client.send(message({
  to: 'agent://analyst',
  intent: 'clarify',
  content: 'Can you verify the revenue figures?'
}));

// Listen for messages
client.on('message', (msg) => {
  console.log(`${msg.from}: ${msg.content}`);
});
```

### Python
```bash
pip install maia-acp
```

```python
from maia_acp import ACPClient, message

client = ACPClient(agent_id="agent://my-agent")

# Send a message
client.send(message(
    to="agent://analyst",
    intent="clarify",
    content="Can you verify the revenue figures?"
))

# Listen for messages
@client.on("message")
def handle(msg):
    print(f"{msg.from_agent}: {msg.content}")
```

## Adapters

ACP works with any agent framework:

```python
# LangChain
from maia_acp.adapters.langchain import ACPLangChainAdapter

# CrewAI
from maia_acp.adapters.crewai import ACPCrewAIAdapter

# AutoGen
from maia_acp.adapters.autogen import ACPAutoGenAdapter
```

## Theatre Integration

ACP events are automatically visualizable with `@maia/theatre`:

```tsx
import { Theatre } from '@maia/theatre';

<Theatre streamUrl="/acp/events" />
```

Every ACP message, handoff, review, and artifact appears in the Theatre live view.

## License

MIT