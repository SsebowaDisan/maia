# Capability-Based Planner Analysis

## Goal
Make Company Agent planning domain-aware (research, docs, email, invoices, analytics, scheduling) while preserving policy gates and existing permissions.

## Why
- Current planning can overfit to a narrow workflow.
- A general company agent needs stronger routing across business capabilities.
- Theatre-first execution needs reliable step-tracking and notes regardless of task type.

## Design
1. Infer required capability domains from:
- Intent tags (`web_research`, `email_delivery`, `docs_write`, etc.).
- Contract actions (`send_email`, `create_document`, `update_sheet`, etc.).
- Keywords (`invoice`, `calendar`, `slack`, `ga4`, `google ads`, etc.).

2. Build a preferred tool set from policy capability matrix:
- Keep only tools available in registry.
- Rank by action class (`read` -> `draft` -> `execute`) to prefer safer exploration first.
- In `company_agent` mode, always keep workspace tracking tools preferred:
`workspace.sheets.track_step`, `workspace.docs.research_notes`.

3. Feed preferred tools into LLM planner prompt and step sorting:
- Keep `allowed_tool_ids` as hard constraints.
- Use preferred tools as soft preference, not a hard lock.

4. Emit theatre-visible capability analysis event:
- Domains selected.
- Preferred tools.
- Signals/rationale used for routing.

## Theatre-First Loop Extension
- Keep existing deep-research behavior.
- Add continuous per-step shadow logging after each completed tool:
  - Append execution note to Google Docs.
  - Mark step `DONE` in Google Sheets with timestamp and evidence URL.
- Continue execution even if Google sync fails; emit warnings and disable further workspace sync safely.

## Safety and Compatibility
- Does not bypass governance or role policy.
- Does not change full-access permissions model.
- Extends planner/orchestration with additive logic.
