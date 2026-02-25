# Maia Company Agent - Phase 1 Guardrails

Status: `Approved`

## Capability Matrix (v1)

| Domain | Tool | Action class | Minimum role |
|---|---|---|---|
| Marketing research | `marketing.web_research` | Read | Analyst |
| Marketing research | `marketing.competitor_profile` | Draft | Member |
| Email | `email.draft` | Draft | Member |
| Email | `email.send` | Execute | Admin |
| Ads analysis | `ads.google.performance` | Read | Analyst |
| Data analysis | `data.dataset.analyze` | Read | Analyst |
| Reporting | `report.generate` | Draft | Member |
| Invoice | `invoice.create` | Draft | Member |
| Invoice | `invoice.send` | Execute | Admin |
| Workplace | `slack.post_message` | Execute | Admin |

## Role Model

- `owner`: workspace owner, full governance authority
- `admin`: operational authority, can run execute actions
- `member`: day-to-day usage with draft and read capabilities
- `analyst`: read-heavy role focused on analysis/research

## Access Modes

- `restricted`
  - Execute-class actions default to confirm-before-execute.
- `full_access`
  - Execute-class actions auto-execute when `agent.full_access_enabled = true`.

## Rules Enforced in Code

- Capability and role mapping are defined in `api/services/agent/policy.py`.
- Access context is derived from settings:
  - `agent.user_role`
  - `agent.access_mode`
  - `agent.full_access_enabled`
  - `agent.tenant_id`
- Runtime policy resolver chooses `auto_execute` or `confirm_before_execute`.

