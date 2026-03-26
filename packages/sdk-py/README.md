# maia-sdk

> The collaboration and observability layer for AI agents. One install, everything you need.

## Install

```bash
pip install maia-sdk
```

With framework adapters:

```bash
pip install maia-sdk[langchain]   # LangChain support
pip install maia-sdk[crewai]      # CrewAI support
pip install maia-sdk[autogen]     # AutoGen support
pip install maia-sdk[all]         # Everything
```

## Quick Start

### 1. Emit ACP events from your agent

```python
from maia_sdk import ACPClient, message, activity, envelope

client = ACPClient(agent_id="agent://researcher")

# Create a message
msg = message(
    from_agent="agent://researcher",
    to="agent://analyst",
    intent="challenge",
    content="The 34% growth figure needs verification.",
    mood="concerned",
)

# Wrap in an event envelope
event = client.emit_message(msg)
print(event.model_dump_json())
```

### 2. Listen to a live stream

```python
from maia_sdk import ACPClient

client = ACPClient(agent_id="agent://observer")
client.connect("http://localhost:8000/acp/events")

@client.on("message")
def on_message(event):
    msg = event.as_message()
    print(f"{msg.from_agent}: {msg.content}")

@client.on("review")
def on_review(event):
    rev = event.as_review()
    print(f"Review: {rev.verdict} — {rev.feedback}")
```

### 3. Wrap existing frameworks

```python
# LangChain
from maia_sdk.adapters.langchain import ACPLangChainAdapter

agent = create_react_agent(llm, tools, prompt)
acp_agent = ACPLangChainAdapter(
    agent=agent,
    agent_id="agent://researcher",
    name="Researcher",
)

for event in acp_agent.run("Find Q4 revenue data"):
    print(event.model_dump_json())

# CrewAI
from maia_sdk.adapters.crewai import ACPCrewAIAdapter

acp_crew = ACPCrewAIAdapter(crew=my_crew)
for event in acp_crew.run():
    print(event.model_dump_json())

# AutoGen
from maia_sdk.adapters.autogen import ACPAutoGenAdapter

acp_chat = ACPAutoGenAdapter(group_chat=my_group_chat)
for event in acp_chat.run("Analyze the data"):
    print(event.model_dump_json())
```

### 4. Serve events as SSE (for Theatre)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from maia_sdk import envelope, message, activity
import json, time

app = FastAPI()

@app.get("/acp/events")
async def stream_events():
    def generate():
        # Your agent logic here — yield ACP events as SSE
        ev = envelope(
            "agent://researcher", "run_1", "message",
            message(
                from_agent="agent://researcher",
                to="agent://analyst",
                intent="propose",
                content="Found 3 key trends in the data.",
            ),
        )
        yield f"data: {ev.model_dump_json()}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

Then point Theatre at it:

```tsx
<Theatre streamUrl="http://localhost:8000/acp/events" />
```

## What's Inside

| Module | What it does |
|--------|-------------|
| `maia_sdk` | ACP protocol — types, client, builders, SSE stream |
| `maia_sdk.adapters.langchain` | Wrap LangChain agents |
| `maia_sdk.adapters.crewai` | Wrap CrewAI crews |
| `maia_sdk.adapters.autogen` | Wrap AutoGen group chats |

## Architecture

```
Your Agent  ──→  maia-sdk  ──→  ACP Events (SSE)  ──→  @maia/sdk (Theatre)
                                      ↑
                              Works with any
                              LLM / framework
```

## License

MIT — Free and open source.

For advanced features (Brain orchestrator, Computer Use, Connectors, Marketplace), see [maia.ai](https://maia.ai).
