# Slice Execution Tracker

Use this file as the live tracker for the active slice only.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Active Slice
- Name: `Google API Capability Expansion (Theatre-First)`
- Status: `done`

## Checklist
- [x] capability planner analysis module integrated (`done`)
- [x] roadmap updated with production API expansion phases (`done`)
- [x] Google API catalog + tool pack registered (`done`)
- [x] unified Google API hub connector implemented (`done`)
- [x] governance/policy coverage validated (`done`)
- [x] end-to-end theatre event visibility validated (`done`)
- [x] explicit theatre surface routing for `api_call_*` events (`done`)
- [x] non-technical business wrapper tools added (route plan / GA4 KPI sheet report / cloud incident digest email) (`done`)
- [x] non-technical business wrapper tools added (invoice workflow / meeting scheduler / proposal workflow) (`done`)
- [x] planner fallback upgraded for non-technical prompts to wrapper tools (`done`)
- [x] registry fallback trace event added to prevent silent tool executions (`done`)
- [x] regression suite green for touched agent modules (`done`)

## Verification Evidence
- Commands run:
- `.venv311\\Scripts\\python.exe -m pytest api/tests/test_agent_capability_planning.py api/tests/test_agent_llm_planner.py api/tests/test_agent_planner.py`
- `.venv311\\Scripts\\python.exe -m compileall api/services/agent/orchestration/step_planner_sections/capability_planning.py api/services/agent/orchestration/step_planner_sections/app.py api/services/agent/orchestration/step_planner_sections/events.py api/services/agent/planner.py api/services/agent/llm_planner.py api/services/agent/orchestration/step_execution_sections/workspace_shadow.py api/services/agent/events.py`
- `.venv311\\Scripts\\python.exe -m pytest api/tests/test_google_api_hub_connector.py api/tests/test_google_api_tools.py api/tests/test_tool_registry.py api/tests/test_agent_capability_planning.py api/tests/test_agent_llm_planner.py api/tests/test_agent_planner.py`
- `.venv311\\Scripts\\python.exe -m compileall api/services/agent/google_api_catalog.py api/services/agent/connectors/google_api_hub_connector.py api/services/agent/connectors/registry.py api/services/agent/tools/google_api_tools.py api/services/agent/tools/registry.py api/services/agent/policy.py api/services/agent/planner.py api/services/agent/events.py`
- `npm run build` (from `frontend/user_interface`)
- `python -m py_compile api/services/agent/tools/google_api_tools.py api/tests/test_google_api_tools.py`
- `.venv311\\Scripts\\python.exe -m pytest api/tests/test_business_workflow_tools.py api/tests/test_agent_planner.py api/tests/test_agent_capability_planning.py api/tests/test_tool_registry.py api/tests/test_google_api_tools.py api/tests/test_agent_llm_planner.py`
- `.venv311\\Scripts\\python.exe -m compileall api/services/agent/tools/business_workflow_tools.py api/services/agent/tools/registry.py api/services/agent/planner.py api/services/agent/llm_planner.py api/services/agent/policy.py api/services/agent/orchestration/step_planner_sections/capability_planning.py api/tests/test_business_workflow_tools.py`
- `.venv311\\Scripts\\python.exe -m pytest api/tests/test_business_workflow_tools.py api/tests/test_business_office_tools.py api/tests/test_agent_planner.py api/tests/test_agent_capability_planning.py api/tests/test_tool_registry.py api/tests/test_google_api_tools.py api/tests/test_agent_llm_planner.py`
- `.venv311\\Scripts\\python.exe -m compileall api/services/agent/tools/business_office_tools.py api/services/agent/tools/business_workflow_tools.py api/services/agent/tools/business_workflow_helpers.py api/services/agent/planner_helpers.py api/services/agent/planner_business_fallback.py api/services/agent/planner.py api/services/agent/tools/registry.py api/services/agent/policy.py api/services/agent/llm_planner.py api/services/agent/orchestration/step_planner_sections/capability_planning.py api/tests/test_business_office_tools.py`
- Test output summary:
- Capability planning and planner suite passed (`14 passed`).
- API hub/catalog/tool/registry/planner suite passed (`23 passed`).
- Frontend build passed after `scene_surface` tab routing changes.
- Wrapper + planner + capability + registry + llm planner validation passed (`29 passed`) using `.venv311`.
- Wrapper + planner + capability + registry + llm planner validation passed (`35 passed`) using `.venv311`.
- LOC gate:
- `api/services/agent/orchestration/step_planner_sections/capability_planning.py` `220`
- `api/services/agent/planner.py` `487`
- `api/services/agent/orchestration/step_execution_sections/workspace_shadow.py` `141`
- `api/services/agent/tools/business_workflow_tools.py` `489`
- `api/services/agent/tools/business_workflow_helpers.py` `35`
- `api/services/agent/tools/business_office_tools.py` `466`
- `api/services/agent/planner_helpers.py` `44`

## Handoff Notes
- Completed in this step:
- Added capability planner routing analysis with theatre-visible `llm.capability_plan` events.
- Extended planner preference flow with `preferred_tool_ids` to bias tool selection by capability domain.
- Added theatre-first per-step shadow sync: append Docs notes + mark Sheets `DONE` with timestamp/evidence.
- Added production API expansion roadmap section to `docs/company_agent_end_to_end_roadmap.md`.
- Added Google API catalog, unified connector, and broad API tool pack scaffolding (in progress validation).
- Added policy + planner allowlist integration for `google.api.*` tool family.
- Added theatre-visible API trace events (`api_call_started`, `api_call_completed`) for live execution transparency.
- Overall status:
- Active API expansion slice validations are complete and ready for next production slice.
