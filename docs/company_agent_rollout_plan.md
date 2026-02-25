# Company Agent Rollout Plan

Status: `Implemented`

## Stage 1 - Internal Alpha

- Enable `agent_mode=company_agent` for internal users.
- Enable read/draft tools only:
  - `marketing.web_research`
  - `marketing.competitor_profile`
  - `ads.google.performance`
  - `data.dataset.analyze`
  - `report.generate`
- Keep execute tools gated by restricted access mode.

## Stage 2 - Controlled Beta

- Enable execute tools for selected workspaces:
  - `email.send`
  - `invoice.send`
  - `slack.post_message`
- Require explicit `agent.full_access_enabled=true` for auto-execute behavior.
- Monitor:
  - tool failure rates
  - event timelines and run logs
  - governance overrides and kill-switch usage

## Stage 3 - Production

- Activate all approved connectors.
- Keep per-tool feature flags in governance API.
- Use instant rollback controls:
  - global kill switch
  - tool-specific disable switches
- Promote with release gates:
  - unit checks
  - frontend build checks
  - audit log validation

