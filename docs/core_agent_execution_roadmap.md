# Maia Core Agent Execution Roadmap

## Rules For Execution
- Only one active slice at a time.
- No file over 500 LOC.
- Use LLM-semantic reasoning for routing and decisions; no hardcoded words as the primary decision mechanism.
- No shortcuts: implement the full slice acceptance path (code, tests, checklist update) before moving on.
- Every user-facing step must meet Apple-level professional quality, with clear and polished "Steve Jobs style" craftsmanship.
- A slice is complete only when:
  - acceptance tests pass
  - regression slice passes
  - checklist is updated to `done`
- Do not start the next slice until the current slice is complete.
- After a slice is marked `done`, automatically move the next `todo` slice to `in_progress` without waiting for a separate user prompt.
- When all slices in a phase are `done`, automatically create/activate the next phase slice and continue execution without waiting for a separate user prompt.
- At the end of each phase, always run a final full regression (`backend pytest`, `frontend npm test`, `frontend npm run build`) before marking the phase complete.
- Delete completed stages from the roadmap when the roadmap work is done, so only active planning content remains.

## Naming Rule (Mandatory)
- Scope: these naming rules apply to Maia modules under `api/` and `frontend/user_interface/src/`, not only UI modules.
- Structure must be domain-first, not prefix-first.
- Do not add new root-level prefix-first modules when an existing Maia domain folder already fits the code.
- Do not add new root-level catch-all modules such as `agent_*`, `browser_*`, `chat_*`, or `manifest_*` if the code belongs under an existing domain path.
- Prefer paths like:
  - `api/services/agent/orchestration/role_router.py`
  - `api/services/agent/execution/browser_event_contract.py`
  - `api/services/agent/tools/workspace/research_notes.py`
  - `frontend/user_interface/src/app/components/agentDesktopScene/InteractionOverlay.tsx`
  - `frontend/user_interface/src/app/components/chatMain/citationFocus.ts`
- Keep names boring and searchable: lowercase folders, snake_case files.
- Any move/rename must update all imports in the same slice and keep tests green.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Execution Slices
Current active slice: `none`

Open slice list:
- none (all listed slices completed and validated)

Rule:
- list only `todo`, `in_progress`, or `blocked` slices in this section
- remove slices from this section once they are `done`

## Next Roadmap
All previously defined phases have been completed and removed from this active roadmap.

When a new roadmap is proposed, add only:
- phases/slices that are not yet done
- acceptance and regression checks for each slice
- current active slice and open slice list
