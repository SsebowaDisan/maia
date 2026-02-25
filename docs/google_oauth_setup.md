# Google OAuth Setup (Local Dev)

This project uses FastAPI backend OAuth callbacks and stores Google tokens server-side.

## Local URLs

- Frontend (Vite): `http://localhost:5173`
- Backend (FastAPI): `http://localhost:8000`

## Google Cloud OAuth Client (Web Application)

In Google Cloud Console, configure:

- Authorized JavaScript origins:
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`
  - Optional (backend-served frontend build): `http://localhost:8000`

- Authorized redirect URIs:
  - `http://localhost:8000/api/agent/oauth/google/callback`
  - Optional host variant: `http://127.0.0.1:8000/api/agent/oauth/google/callback`

## Required Env Vars

Set in `.env` (do not commit secrets):

```env
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/agent/oauth/google/callback
```

Optional:

```env
GOOGLE_OAUTH_SCOPES=openid,email,profile,https://www.googleapis.com/auth/gmail.compose,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/analytics.readonly
GOOGLE_OAUTH_FRONTEND_SUCCESS_URL=http://localhost:5173/settings?oauth=success
GOOGLE_OAUTH_FRONTEND_ERROR_URL=http://localhost:5173/settings?oauth=error
```

## Endpoints

- Start OAuth:
  - `GET /api/agent/oauth/google/start`
- Callback (Google redirects here):
  - `GET /api/agent/oauth/google/callback`
- Connection status:
  - `GET /api/agent/oauth/google/status`
- Disconnect and revoke:
  - `POST /api/agent/oauth/google/disconnect`
- Live events stream (SSE):
  - `GET /api/agent/events`

## Quick API Smoke Test (Local)

```bash
# 1) Start OAuth, then open authorize_url in browser.
curl -s -H "X-User-Id: default" "http://localhost:8000/api/agent/oauth/google/start"

# 2) After consent + callback, verify connection.
curl -s -H "X-User-Id: default" "http://localhost:8000/api/agent/oauth/google/status"

# 3) Dry-run Gmail send via company agent flow (no dispatch).
curl -s -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: default" \
  -d '{
    "message": "gmail send dry run to owner@example.com subject Monthly report update",
    "agent_mode": "company_agent",
    "access_mode": "full_access",
    "index_selection": {}
  }'

# 4) Disconnect and revoke.
curl -s -X POST -H "X-User-Id: default" "http://localhost:8000/api/agent/oauth/google/disconnect"
```

## Troubleshooting `redirect_uri_mismatch`

If you see `redirect_uri_mismatch`:

1. Confirm the redirect URI in Google Cloud exactly matches:
   - `http://localhost:8000/api/agent/oauth/google/callback`
2. Confirm `.env` value for `GOOGLE_OAUTH_REDIRECT_URI` is identical.
3. Restart backend after changing `.env`.
4. Ensure you are not mixing `localhost` and `127.0.0.1` without adding both.
5. Ensure you are using OAuth client type **Web application**.
