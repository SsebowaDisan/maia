# Company Agent Operational Playbook

Status: `Implemented`

## Primary Operations

- Monitor run outcomes via:
  - `GET /api/agent/runs`
  - `GET /api/agent/runs/{run_id}/events`
- Monitor connector readiness via:
  - `GET /api/agent/connectors/health`
- Manage runtime controls via:
  - `GET /api/agent/governance`
  - `PATCH /api/agent/governance`

## Incident Runbooks

### Provider outage

1. Disable affected tool with governance API.
2. Keep read-only tools enabled.
3. Re-enable after connector health returns `ok=true`.

### Token expiry or credential drift

1. Update connector credentials via:
   - `POST /api/agent/connectors/credentials`
2. Verify health endpoint.
3. Trigger a test run.

### Email delivery failure

1. Check SMTP settings (`agent.smtp_*`).
2. Run `email.draft` first.
3. Retry `email.send` with confirmation in restricted mode.

### Ads API quota or data quality issues

1. Fall back to local metrics payload for analysis tool.
2. Log limitation in report output.
3. Schedule re-run after quota reset.

### Invoice send failure

1. Keep invoice PDF artifact in `.maia_agent/invoices/`.
2. Retry `invoice.send` after connector health check.
3. Notify owner/admin via Slack/email if configured.

## Monthly Quality Review

- Review top failed tools and reasons from audit logs.
- Review average steps per run and completion rates.
- Review governance events (kill switch usage, disabled tools).

