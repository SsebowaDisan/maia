# Maia React UI

Primary UI for Maia. This app is served by Vite in local development and by FastAPI static hosting in packaged deployments.

## Local development

1. Install frontend dependencies:
   ```bash
   npm install
   ```
2. Ensure backend API is running from repo root:
   ```bash
   python run_api.py
   ```
3. Run the frontend:
   ```bash
   npm run dev
   ```

Default dev URLs:
- UI: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`

## Environment variables

Use `.env.example` as the baseline:
- `VITE_API_BASE_URL`: backend origin (defaults to `http://127.0.0.1:8000` in dev inference)
- `VITE_USER_ID`: default user identity header for API calls
