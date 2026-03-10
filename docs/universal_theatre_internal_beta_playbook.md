# Universal Theatre Internal Beta Playbook

## Goal
Validate the staged Theatre UX with an internal cohort before broad rollout.

Related docs:
- [universal_theatre_rollout_guardrails.md](/Users/disanssebowabasalidde/Documents/GitHub/maia/docs/universal_theatre_rollout_guardrails.md)
- [universal_theatre_internal_beta_report_template.md](/Users/disanssebowabasalidde/Documents/GitHub/maia/docs/universal_theatre_internal_beta_report_template.md)

## Cohort
- PM + Design + Frontend + Backend + QA representatives
- 10-20 internal users across mixed task types (web, docs, sheets, email, API/SAP)

## Test Scenarios
1. Web research to email draft flow
2. Docs and sheets update flow
3. API/SAP data retrieval with review gate
4. Error/blocked/needs-input flow

## Instrumentation Inputs
- `maia:theatre_metric` stage transition events
- Manual tab override metrics
- `understand_to_surface_ms`
- `surface_to_review_ms`

## Structured Feedback Template
- Was the current stage always clear? (`yes/no`, notes)
- Was task breakdown helpful? (`1-5`, notes)
- Did content appear too early? (`never/sometimes/often`)
- Was confirmation gating clear before irreversible actions? (`yes/no`, notes)
- Preferred pacing (`too slow`, `good`, `too fast`)

## Exit Criteria
- No critical confusion issues in stage flow
- No premature surface reveal defects
- Confirmation stage understood by >90% of participants
- At least one improvement iteration completed from beta findings
