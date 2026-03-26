# @maia/sdk

> The collaboration and observability layer for AI agents. One install, everything you need.

## Install

```bash
npm install @maia/sdk
```

## Quick Start

### 1. Connect agents (protocol)

```typescript
import { ACPClient, message, handoff } from '@maia/sdk';

// Create a client for your agent
const client = new ACPClient({ agentId: 'agent://researcher' });

// Connect to a live event stream
client.connect('http://localhost:3000/acp/events');

// Listen for messages from other agents
client.on('message', (event) => {
  const msg = event.payload;
  console.log(`${msg.from}: ${msg.content}`);
});

// Send a message to another agent
const msg = message({
  from: 'agent://researcher',
  to: 'agent://analyst',
  intent: 'challenge',
  content: 'The 34% growth figure needs verification.',
});
```

### 2. Visualize agents (Theatre)

```tsx
import { Theatre } from '@maia/sdk/theatre';

// Live mode — watch agents collaborate in real-time
<Theatre streamUrl="/acp/events" />

// Replay mode — DVR for past runs
<Theatre recordedEvents={events} />

// With budget tracking
<Theatre streamUrl="/acp/events" budgetUsd={5.00} showThinking />
```

### 3. Use individual components

```tsx
import {
  TeamThread,       // Slack-like agent chat
  ActivityTimeline, // Tool calls, browser actions
  TheatreDesktop,   // Maia desktop shell
  CostBar,          // Live cost counter
  ReplayControls,   // DVR controls
  AgentAvatar,      // Agent identity
  useACPStream,     // Hook: connect to SSE
  useReplay,        // Hook: replay events
} from '@maia/sdk/theatre';
```

### 4. Use the Maia desktop shell

```tsx
import { TheatreDesktop } from '@maia/sdk/theatre';

<TheatreDesktop
  streaming
  roleLabel="Browser"
  statusText="Reviewing the target website"
  sceneTransitionLabel="Analysis"
>
  <YourScene />
</TheatreDesktop>
```

### 5. Use the Maia default look or override it

`@maia/sdk/theatre` now ships with the Maia app look as the default theme. If you render `Theatre`, `TeamThread`, `ActivityTimeline`, or `MessageBubble` without a theme prop, they use the Maia visual system automatically.

```tsx
import { Theatre, maiaTheme } from '@maia/sdk/theatre';

// Maia look by default
<Theatre streamUrl="/acp/events" />

// Override only the parts you want
<Theatre
  streamUrl="/acp/events"
  theme={{
    theatre: {
      shell: `${maiaTheme.theatre.shell} ring-1 ring-sky-500/20`,
    },
    bubble: {
      card: `${maiaTheme.bubble.card} bg-sky-50/80`,
    },
  }}
/>
```

## What's Inside

| Module | What it does |
|--------|-------------|
| `@maia/sdk` | ACP protocol — types, client, builders, SSE parser |
| `@maia/sdk/theatre` | React components — Theatre, TeamThread, CostBar, Replay |

## Works With Any SSE Stream

Theatre doesn't require ACP-native events. Point it at **any** Server-Sent Events endpoint and it will intelligently wrap the events for visualization:

```tsx
// Your existing agent stream — no changes needed
<Theatre streamUrl="/my-existing-agent/events" />
```

## Architecture

```
Your Agent  ──→  ACP Events  ──→  Theatre (visualization)
                     ↑
              Works with any
              SSE/JSON stream
```

## License

MIT — Free and open source.

For advanced features (Brain orchestrator, Computer Use, Connectors, Marketplace), see [maia.ai](https://maia.ai).
