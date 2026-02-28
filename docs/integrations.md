# Integrations Configuration

This project uses server-side integration credentials. Do not store integration secrets in the browser.

## Google OAuth (Source of Truth)

Google Workspace integrations (Gmail, Calendar, Drive, Docs, Sheets, GA4) use OAuth tokens stored server-side.

Required env vars:

```env
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/agent/oauth/google/callback
```

OAuth endpoints:

- `GET /api/agent/oauth/google/start`
- `GET /api/agent/oauth/google/callback`
- `GET /api/agent/oauth/google/status`
- `POST /api/agent/oauth/google/disconnect`

## Maps API Key

Server-side Maps key resolution order:

1. `GOOGLE_MAPS_API_KEY`
2. `GOOGLE_PLACES_API_KEY`
3. `GOOGLE_GEO_API_KEY`
4. Stored connector secret (`google_maps`) from API save endpoint

Recommended env var:

```env
GOOGLE_MAPS_API_KEY=
```

API endpoints:

- `GET /api/agent/integrations/maps/status`
- `POST /api/agent/integrations/maps/save`
- `POST /api/agent/integrations/maps/clear`

The backend never returns the key value in API responses.

## Brave Search API

Recommended env var:

```env
BRAVE_SEARCH_API_KEY=
```

API endpoints:

- `GET /api/agent/integrations/brave/status`
- `POST /api/agent/tools/web_search`

Tool-level behavior:

- `marketing.web_research` prefers Brave Search first
- falls back to Bing only when Brave is unavailable
- no DuckDuckGo manual fallback links are emitted in agent responses
- emits live events (`status`, `brave.search.query`, `brave.search.results`) through SSE

## Ollama Local Models

Maia can manage Ollama model downloads directly from Settings so users can pull and activate local models without manual resource editing.

Recommended env var:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Ollama API endpoints used (official):

- `GET /api/version`
- `GET /api/tags`
- `POST /api/pull` (streaming progress)

Maia API endpoints:

- `GET /api/agent/integrations/ollama/status`
- `GET /api/agent/integrations/ollama/quickstart`
- `POST /api/agent/integrations/ollama/start`
- `POST /api/agent/integrations/ollama/config`
- `GET /api/agent/integrations/ollama/models`
- `POST /api/agent/integrations/ollama/pull`
- `POST /api/agent/integrations/ollama/select`
- `POST /api/agent/integrations/ollama/embeddings/select`
- `POST /api/agent/integrations/ollama/embeddings/apply-all`

Behavior:

- Pulls model by name (e.g. `qwen3:8b`, `llama3.1:8b`, `deepseek-r1:8b`) from Ollama.
- Streams pull progress as live events (`ollama.pull.started`, `ollama.pull.progress`, `ollama.pull.completed`).
- Automatically creates/updates a Maia LLM entry using Ollama's OpenAI-compatible endpoint and sets it as default.
- Includes a one-click setup flow in Settings that saves URL, starts Ollama, downloads recommended chat+embedding models, and activates both.
- Supports one-click local startup from Settings (`Start Ollama`), including quickstart command hints.
- Supports selecting an Ollama embedding model (recommended: `embeddinggemma`, `qwen3-embedding:0.6b`, `nomic-embed-text`) for local indexing.
- Supports one-click embedding migration across all index collections and automatically queues full reindex jobs for existing files/URLs.

## Gmail Live Desktop (Playwright)

`gmail.draft` and `gmail.send` now support real Playwright desktop execution so the theater shows actual browser actions and snapshots.

Recommended env vars:

```env
AGENT_GMAIL_PLAYWRIGHT_HEADLESS=true
AGENT_GMAIL_PLAYWRIGHT_SLOW_MO_MS=50
AGENT_GMAIL_PLAYWRIGHT_PROFILE_DIR=.maia_agent/playwright/gmail_profile
```

Behavior:

- Opens search engine and searches `gmail`
- Opens Gmail web UI
- Fills recipient, subject, and body
- Sends message with real UI click (`gmail.send`) or leaves draft (`gmail.draft`)
- Emits snapshot-backed events (`email_open_compose`, `email_type_body`, `email_click_send`, `email_sent`)

Important:

- First run may require manual Gmail web sign-in in the Playwright profile.
- If sign-in is required, event `email_auth_required` is emitted.
- By default, tools fall back to Gmail API if desktop mode is unavailable.
- Set `desktop_required=true` in tool params to enforce desktop-only execution.

Optional bootstrap command (one-time login):

```bash
python scripts/gmail_playwright_login.py
```

## Live Events (SSE)

- `GET /api/agent/events`

Used by Settings and agent UI to render recent timeline updates for OAuth, tool execution, and search actions.
