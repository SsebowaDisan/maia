# Integration and Runtime Baseline

## Integration Baseline
### Connector Framework
- connectors are registered through a central registry
- each connector encapsulates provider auth and API contracts
- tools consume connectors through stable connector IDs

### Baseline Provider Coverage
- Gmail API and DWD mailer service
- Brave web search
- Google Workspace connectors (docs, sheets, drive)
- Google Ads and Analytics connectors
- Maps/Places connectors
- Slack connector
- Invoice connector abstraction

## Runtime Baseline
### Execution Context
- each run includes user_id, tenant_id, conversation_id, run_id, mode, settings
- orchestrator drives tool execution under access-context policy

### Deployment and Environment
- local dev runtime supported through Python virtual environment
- containerized runtime path supported for deployment
- environment-driven config controls for connector credentials and behavior

### Health and Validation
- provider status endpoints expose configuration/reachability state where supported
- connector errors are normalized into actionable messages
- activity events provide operational visibility during execution

## Configuration and Secret Controls
- settings service persists user/tenant-scoped controls
- credential store keeps provider secrets server-side
- no hardcoded secrets in repository

## Baseline Acceptance Validation
- connector tests for Gmail, Brave, and analytics-related paths pass
- DWD sender tests pass for MIME/base64url/payload correctness
- policy and tool-registry checks pass for RBAC and execution control

