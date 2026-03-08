# Maia Source Refactoring Roadmap

## Rules For Execution
1. Only one active slice at a time.
2. No file over 500 LOC.
3. A slice is complete only when:
   - acceptance tests pass
   - regression slice passes
   - checklist is updated to `done`
4. Do not start the next slice until the current slice is complete.
5. Use LLM reasoning for semantic decisions; do not rely on hardcoded words or shortcut phrase matching.
6. No shortcuts in delivery quality: every step must be production-grade and complete.
7. End-user surfaces must stay Apple-like: low noise, strong hierarchy, calm motion, clear typography, no debug leakage.
8. Keep the execution quality professional and consistent with the roadmap design standards.
9. When this roadmap is completed, remove or delete completed stages so the active roadmap only contains unfinished work.

## Goal
Refactor all source code files above 500 LOC to below 500 LOC while preserving behavior, tests, and user experience.

## Scope Input
- Source file inventory is maintained in [files_over_500_loc.md](/Users/disanssebowabasalidde/Documents/GitHub/maia/docs/files_over_500_loc.md).
- Current target count: 55 source files above 500 LOC.

## Naming Rule
- Scope: these naming rules apply to all modules under `api/` and `frontend/user_interface/src/`.
- Structure must be domain-first, not prefix-first.
- Keep names boring and searchable: lowercase folders, snake_case files for Python, and consistent component naming for React files.
- Prefer grouped paths like:
- `frontend/user_interface/src/app/components/infoPanel/review/SourceBar.tsx`
- `frontend/user_interface/src/app/components/infoPanel/review/ReviewViewer.tsx`
- `frontend/user_interface/src/app/components/infoPanel/evidence/EvidenceStrip.tsx`
- `frontend/user_interface/src/app/components/mindmapViewer/context/ContextMindmapViewer.tsx`
- Any move or rename must update imports in the same slice and keep tests green.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Execution Policy For This Refactor
- Every slice must reduce at least one oversized file to `<500 LOC`.
- No behavior rewrites in refactor-only slices; extract/move/split with parity tests.
- For each touched area:
  - run targeted acceptance tests first
  - run cross-area regression second
  - update slice status to `done` only after green checks

## Active Phases

### Phase R1: Chat Backend Decomposition
Status: `in_progress`

#### Slice R1.1
Status: `in_progress`
Targets:
- `api/services/chat/citations.py` (2388)
Plan:
- split into domain modules: parsing, normalization, inline citation rendering, evidence linking, and HTML post-processing
- keep public API compatibility via thin facade exports
Acceptance:
- `PYTHONPATH=. pytest -q api/tests/test_chat_citations.py`
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_chat_citations.py api/tests/test_fast_qa_api.py`

#### Slice R1.2
Status: `todo`
Targets:
- `api/services/chat/app.py` (2187)
- `api/services/chat/fast_qa.py` (1968)
- `api/services/chat/fast_qa_retrieval.py` (606)
Acceptance:
- `PYTHONPATH=. pytest -q api/tests/test_fast_qa_api.py`
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_chat_citations.py api/tests/test_fast_qa_api.py`

#### Slice R1.3
Status: `todo`
Targets:
- `api/services/chat/fast_qa.py` residual >500 parts
- shared chat support modules created in R1.1/R1.2
Acceptance:
- `PYTHONPATH=. pytest -q api/tests/test_fast_qa_api.py`
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_chat_citations.py api/tests/test_fast_qa_api.py`

### Phase R2: Agent Contracts, Planning, and Orchestration
Status: `todo`

#### Slice R2.1
Status: `todo`
Targets:
- `api/services/agent/llm_contracts.py` (1178)
- `api/tests/test_agent_llm_contracts.py` (1107)
Acceptance:
- `PYTHONPATH=. pytest -q api/tests/test_agent_llm_contracts.py`
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_agent_llm_contracts.py api/tests/test_agent_planner.py`

#### Slice R2.2
Status: `todo`
Targets:
- `api/services/agent/planner.py` (858)
- `api/services/agent/orchestration/task_preparation.py` (740)
- `api/services/agent/orchestration/finalization.py` (988)
Acceptance:
- `PYTHONPATH=. pytest -q api/tests/test_agent_planner.py`
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_agent_planner.py api/tests/test_agent_step_planner_research_and_logging.py`

#### Slice R2.3
Status: `todo`
Targets:
- `api/services/agent/orchestration/app.py` (782)
- `api/services/agent/contract_verification.py` (599)
- `api/services/agent/llm_response_formatter.py` (693)
Acceptance:
- `PYTHONPATH=. pytest -q api/tests/test_agent_step_planner_research_and_logging.py`
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_agent_planner.py api/tests/test_agent_step_planner_research_and_logging.py`

### Phase R3: Agent Tools and Connectors
Status: `todo`

#### Slice R3.1
Status: `todo`
Targets:
- `api/services/agent/tools/research_tools.py` (1736)
- `api/services/agent/tools/web_extract_tools.py` (646)
- `api/services/agent/connectors/browser_connector.py` (1056)
Acceptance:
- targeted tests for research/browser toolchain in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_agent_step_planner_research_and_logging.py`

#### Slice R3.2
Status: `todo`
Targets:
- `api/services/agent/tools/document_highlight_tools.py` (824)
- `api/services/agent/tools/browser_tools.py` (616)
- `api/services/agent/llm_execution_support_parts/polishing.py` (550)
Acceptance:
- targeted tests for document/browser rendering contracts in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_chat_citations.py api/tests/test_agent_step_planner_research_and_logging.py`

#### Slice R3.3
Status: `todo`
Targets:
- `api/services/agent/tools/gmail_tools.py` (806)
- `api/services/agent/tools/data_tools.py` (781)
- `api/services/agent/tools/business_workflow_tools.py` (514)
- `api/services/agent/tools/data_science/visualization_tool.py` (537)
Acceptance:
- targeted tests for mail/data/business tools in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_agent_planner.py api/tests/test_agent_step_planner_research_and_logging.py`

### Phase R4: Upload, Ingestion, Routers, and Service Splits
Status: `todo`

#### Slice R4.1
Status: `todo`
Targets:
- `api/services/upload/indexing.py` (1647)
- `api/services/upload/groups.py` (589)
Acceptance:
- upload/indexing targeted tests in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests`

#### Slice R4.2
Status: `todo`
Targets:
- `api/routers/uploads.py` (612)
- `api/routers/web_preview.py` (901)
- `api/services/ingestion/manager.py` (979)
Acceptance:
- router and preview targeted tests in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests`

#### Slice R4.3
Status: `todo`
Targets:
- `api/services/mindmap_service.py` (606)
- `api/services/google/auth.py` (704)
- `api/routers/integrations_api/ollama.py` (541)
Acceptance:
- targeted service integration tests in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests`

### Phase R5: Frontend Chat and Shell Decomposition
Status: `todo`

#### Slice R5.1
Status: `todo`
Targets:
- `frontend/user_interface/src/app/components/ChatSidebar.tsx` (2205)
Acceptance:
- `npm test -- ChatSidebar`
Regression:
- `npm test`

#### Slice R5.2
Status: `todo`
Targets:
- `frontend/user_interface/src/app/components/chatMain/TurnsPanel.tsx` (759)
- `frontend/user_interface/src/app/components/chatMain/ComposerPanel.tsx` (658)
- `frontend/user_interface/src/app/components/chatMain/useChatMainInteractions.ts` (704)
Acceptance:
- chat main targeted tests in this slice
Regression:
- `npm test`

#### Slice R5.3
Status: `todo`
Targets:
- `frontend/user_interface/src/app/appShell/useConversationChat.ts` (884)
- `frontend/user_interface/src/app/appShell/useFileLibrary.ts` (618)
- `frontend/user_interface/src/app/appShell/app.tsx` (541)
Acceptance:
- app-shell targeted tests in this slice
Regression:
- `npm test && npm run build`

### Phase R6: Frontend Verification and Settings Decomposition
Status: `todo`

#### Slice R6.1
Status: `todo`
Targets:
- `frontend/user_interface/src/app/components/PdfEvidenceMap.tsx` (1410)
- `frontend/user_interface/src/app/components/mindmapViewer/MindMapViewer.tsx` (572)
Acceptance:
- mindmap/evidence targeted tests in this slice
Regression:
- `npm test`

#### Slice R6.2
Status: `todo`
Targets:
- `frontend/user_interface/src/app/components/settings/tabs/IntegrationsSettings.tsx` (1023)
- `frontend/user_interface/src/app/components/settings/useSettingsController.ts` (509)
- `frontend/user_interface/src/app/components/filesView/useFilesViewActions.ts` (521)
Acceptance:
- settings/files targeted tests in this slice
Regression:
- `npm test`

#### Slice R6.3
Status: `todo`
Targets:
- `frontend/user_interface/src/app/components/agentActivityPanel/app.tsx` (763)
- `frontend/user_interface/src/app/components/agentActivityPanel/useAgentActivityDerived.ts` (505)
- `frontend/user_interface/src/styles/theme.css` (806)
Acceptance:
- activity panel/theatre targeted tests in this slice
Regression:
- `npm test && npm run build`

### Phase R7: Library Module Decomposition
Status: `todo`

#### Slice R7.1
Status: `todo`
Targets:
- `libs/maia/maia/indices/qa/citation_qa.py` (550)
- `libs/ktem/ktem/reasoning/rewoo.py` (503)
- `libs/ktem/ktem/pages/chat/chat_page/events.py` (522)
Acceptance:
- library targeted tests in this slice
Regression:
- `PYTHONPATH=. pytest -q libs`

#### Slice R7.2
Status: `todo`
Targets:
- `libs/ktem/ktem/index/file/graph/lightrag_pipelines.py` (550)
- `libs/ktem/ktem/index/file/graph/nano_pipelines.py` (549)
- `libs/ktem/ktem/index/file/file_ui/file_index_events.py` (517)
Acceptance:
- graph/index targeted tests in this slice
Regression:
- `PYTHONPATH=. pytest -q libs`

### Phase R8: Final Full-System Verification and Cleanup
Status: `todo`

#### Slice R8.1
Status: `todo`
Targets:
- verify all previously oversized source files are `<500 LOC`
- remove resolved entries from [files_over_500_loc.md](/Users/disanssebowabasalidde/Documents/GitHub/maia/docs/files_over_500_loc.md)
Acceptance:
- `git ls-files -z | xargs -0 wc -l | awk '$2 != "total" && $1 > 500 && $2 ~ /\\.(py|ts|tsx|js|jsx|css|scss|html|htm|sql|sh|bash|zsh|yaml|yml|toml|ini|cfg|conf|go|rs|java|kt|swift|rb|php|c|cc|cpp|h|hpp)$/'` returns empty
Regression:
- `PYTHONPATH=. pytest -q`
- `npm test`
- `npm run build`
