# Strategic Scope and Governance Alignment

## Objective
Define the operating boundary for the Company Agent with clear accountabilities, risk controls, and acceptance criteria.

## Scope Catalog
### Research and Intelligence
- market and competitor research with source citations
- website and document evidence extraction
- executive summaries with confidence notes

### Analytics and Reporting
- dataset profiling and KPI summaries
- chart artifact generation
- scheduled and on-demand report generation

### Communication and Delivery
- server-side report delivery via Mailer Service
- notification dispatch to approved collaboration channels

### Business Operations
- invoice drafting and send workflows
- workspace document automation
- campaign and performance analysis modules

## Stakeholder Ownership Matrix
- Legal: policy, compliance, retention, redaction requirements
- Marketing: research quality, campaign insight usefulness
- HR: approved HR content boundaries, hiring/onboarding artifact standards
- Finance: invoice and financial summary controls
- IT/Security: secrets, RBAC, auditability, incident controls
- Product/Operations: workflow quality and runbook readiness

## Governance Baseline
- RBAC enforced for all tools and connector actions.
- Confirm-before-execute required in restricted mode for high-risk actions.
- All execute actions produce audit entries with run, tenant, user, and tool context.
- Evidence traceability required for research and analytical conclusions.
- Sensitive credentials must be sourced from server-side secret/config stores only.

## Out-of-Scope (Current Program)
- autonomous contract finalization without approval
- unrestricted write access across tenant boundaries
- direct secret handling in frontend clients

## Completion Criteria
- Capability catalog approved by all owners.
- Governance baseline approved and documented.
- Acceptance criteria catalog exists and is test-linked.

