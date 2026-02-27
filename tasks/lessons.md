# Correction Lessons Log

Append one entry after each user correction that changes expected behavior.

## Entry Template
- Date:
- Slice:
- User correction:
- Root cause:
- Preventive rule:
- Verification added:
- Owner:

## Entries
- Date: 2026-02-27
- Slice: Clarification Gate and Missing Requirement Detection
- User correction: Remove noisy theatre keyword cards and stabilize screen transitions while keeping live docs/sheets behavior.
- Root cause: Scene rendering mixed operational overlays with primary surfaces and switched tabs directly from raw event stream.
- Preventive rule: Keep theatre overlays minimal, reserve screen transitions for explicit scene events, and fall back to the latest valid snapshot to avoid flicker.
- Verification added: Frontend production build plus targeted backend test suite for task-contract/plan flows.
- Owner: Codex
