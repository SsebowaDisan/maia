# Universal Theatre Rollout Guardrails

## Purpose
Define objective telemetry thresholds, alerting, and rollback criteria for staged Theatre rollout.

## Core Metrics
- `system_first_compliance_rate`
- `premature_surface_reveal_rate`
- `roadmap_visibility_rate`
- `manual_override_rate`
- `manual_override_resume_success_rate`
- `blocked_flow_recovery_rate`
- `needs_input_recovery_rate`
- `error_recovery_rate`
- `understand_to_surface_ms_p95`
- `surface_to_review_ms_p95`

## Canary Thresholds
| Metric | Target | Warn | Rollback Trigger |
|---|---|---|---|
| `system_first_compliance_rate` | >= 0.98 | < 0.96 | < 0.92 |
| `premature_surface_reveal_rate` | <= 0.01 | > 0.02 | > 0.05 |
| `roadmap_visibility_rate` | >= 0.95 | < 0.92 | < 0.88 |
| `manual_override_resume_success_rate` | >= 0.95 | < 0.92 | < 0.85 |
| `blocked_flow_recovery_rate` | >= 0.90 | < 0.85 | < 0.75 |
| `error_recovery_rate` | >= 0.90 | < 0.85 | < 0.75 |
| `understand_to_surface_ms_p95` | <= 6000 | > 8000 | > 12000 |
| `surface_to_review_ms_p95` | <= 20000 | > 30000 | > 45000 |

## Rollout Stages
1. `0%` disabled baseline capture
2. `5%` internal canary
3. `25%` limited rollout
4. `50%` broad rollout
5. `100%` default-on

Promotion rule:
- promote only when no rollback trigger is hit for 48h and no unresolved P1/P2 theatre defects are open.

Rollback rule:
- immediate rollback to previous flag level if any rollback trigger is crossed for 2 consecutive 1h windows.

## Alerting
- Warn threshold breach: notify product + engineering channel.
- Rollback threshold breach: page on-call and auto-open incident.

## Operational Checklist
- verify `VITE_STAGED_THEATRE_ENABLED` and `MAIA_STAGED_THEATRE_ENABLED` values per environment.
- verify metrics ingestion for `maia:theatre_metric` events before canary starts.
- confirm run-level sampling includes browser/docs/sheets/email/api flows.

