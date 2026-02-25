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
- falls back to Bing, then DuckDuckGo
- emits live events (`status`, `brave.search.query`, `brave.search.results`) through SSE

## Live Events (SSE)

- `GET /api/agent/events`

Used by Settings and agent UI to render recent timeline updates for OAuth, tool execution, and search actions.
