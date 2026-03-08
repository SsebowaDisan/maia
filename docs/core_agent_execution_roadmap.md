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
- Current target count: 38 source files above 500 LOC.

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
Status: `done`

#### Slice R1.1
Status: `done`
Targets:
- `api/services/chat/citations.py` (2388)
Plan:
- split into domain modules: parsing, normalization, inline citation rendering, evidence linking, and HTML post-processing
- keep public API compatibility via thin facade exports
Acceptance:
- `PYTHONPATH=.:libs/ktem:libs/maia pytest -q api/tests/test_chat_citations.py`
Regression:
- `PYTHONPATH=.:libs/ktem:libs/maia pytest -q api/tests/test_chat_citations.py api/tests/test_fast_qa_general_fallback.py api/tests/test_fast_qa_retrieval.py`

#### Slice R1.2
Status: `done`
Targets:
- `api/services/chat/app.py` (2187)
- `api/services/chat/fast_qa.py` (1968) -> done (`api/services/chat/fast_qa.py` now 498 LOC with facade-compatible helper split)
- `api/services/chat/fast_qa_retrieval.py` (606) -> done (`api/services/chat/fast_qa_retrieval.py` now 273 LOC)
Acceptance:
- `PYTHONPATH=.:libs/ktem:libs/maia pytest -q api/tests/test_fast_qa_retrieval.py`
Regression:
- `PYTHONPATH=.:libs/ktem:libs/maia pytest -q api/tests/test_chat_citations.py api/tests/test_fast_qa_general_fallback.py api/tests/test_fast_qa_retrieval.py`
Validation:
- Acceptance passed: 16 passed.
- Regression passed: 66 passed.

#### Slice R1.3
Status: `done`
Targets:
- `api/services/chat/app.py` residual >500 parts
- shared chat orchestration support modules created in R1.2
Acceptance:
- `PYTHONPATH=.:libs/ktem:libs/maia pytest -q api/tests/test_chat_auto_web_fallback.py`
Regression:
- `PYTHONPATH=.:libs/ktem:libs/maia pytest -q api/tests/test_chat_citations.py api/tests/test_fast_qa_general_fallback.py api/tests/test_fast_qa_retrieval.py api/tests/test_chat_auto_web_fallback.py`
Validation:
- `api/services/chat/app.py` refactored to helper-facade architecture and reduced to 324 LOC.
- Acceptance passed: 17 passed.
- Regression passed: 83 passed.

### Phase R2: Agent Contracts, Planning, and Orchestration
Status: `done`

#### Slice R2.1
Status: `done`
Targets:
- `api/services/agent/llm_contracts.py` (1178)
- `api/tests/test_agent_llm_contracts.py` (1107)
Acceptance:
- `PYTHONPATH=. pytest -q api/tests/test_agent_llm_contracts.py`
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_agent_llm_contracts.py api/tests/test_agent_planner.py`
Validation:
- `api/services/agent/llm_contracts.py` reduced to 473 LOC with helper decomposition into:
  - `api/services/agent/llm_contracts_base.py`
  - `api/services/agent/llm_contracts_helpers.py`
  - `api/services/agent/llm_contracts_requirements.py`
- `api/tests/test_agent_llm_contracts.py` reduced to 4 LOC with split test case modules:
  - `api/tests/agent_contract_cases/build_cases_part1.py`
  - `api/tests/agent_contract_cases/build_cases_part2.py`
  - `api/tests/agent_contract_cases/verify_cases.py`
  - `api/tests/agent_contract_cases/probe_cases.py`
- Acceptance passed: 38 passed (`PYTHONPATH=. pytest -q api/tests/test_agent_llm_contracts.py`).
- Regression passed: 67 passed (`PYTHONPATH=. pytest -q api/tests/test_agent_llm_contracts.py api/tests/test_agent_planner.py`).

#### Slice R2.2
Status: `done`
Targets:
- `api/services/agent/planner.py` (858)
- `api/services/agent/orchestration/task_preparation.py` (740)
- `api/services/agent/orchestration/finalization.py` (988)
Acceptance:
- `PYTHONPATH=. pytest -q api/tests/test_agent_planner.py`
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_agent_planner.py api/tests/test_agent_step_planner_research_and_logging.py`
Validation:
- `api/services/agent/planner.py` reduced to 445 LOC and normalized via split support modules.
- `api/services/agent/orchestration/task_preparation.py` reduced to 496 LOC with helper-driven contract/context extraction.
- `api/services/agent/orchestration/finalization.py` reduced to 498 LOC with extracted scope/persistence helpers:
  - `api/services/agent/orchestration/finalization_scope.py`
  - `api/services/agent/orchestration/finalization_persistence.py`
- Acceptance passed: 29 passed (`PYTHONPATH=. pytest -q api/tests/test_agent_planner.py`).
- Regression passed: 55 passed (`PYTHONPATH=. pytest -q api/tests/test_agent_planner.py api/tests/test_agent_step_planner_research_and_logging.py`).
- Additional safeguard passed: 5 passed (`PYTHONPATH=. pytest -q api/tests/test_agent_finalization_info_html.py`).

#### Slice R2.3
Status: `done`
Targets:
- `api/services/agent/orchestration/app.py` (782)
- `api/services/agent/contract_verification.py` (599) -> done (`api/services/agent/contract_verification.py` now 271 LOC)
- `api/services/agent/llm_response_formatter.py` (693)
Acceptance:
- `PYTHONPATH=. pytest -q api/tests/test_agent_step_planner_research_and_logging.py`
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_agent_planner.py api/tests/test_agent_step_planner_research_and_logging.py`
Validation:
- `api/services/agent/orchestration/app.py` reduced to 487 LOC with extracted run/runtime helpers in:
  - `api/services/agent/orchestration/app_runtime_helpers.py`
- `api/services/agent/llm_response_formatter.py` reduced to 348 LOC with text/citation cleanup extracted to:
  - `api/services/agent/llm_response_formatter_text_ops.py`
- Acceptance passed: 26 passed (`PYTHONPATH=. pytest -q api/tests/test_agent_step_planner_research_and_logging.py`).
- Regression passed: 55 passed (`PYTHONPATH=. pytest -q api/tests/test_agent_planner.py api/tests/test_agent_step_planner_research_and_logging.py`).
- Additional safeguards passed:
  - `PYTHONPATH=. pytest -q api/tests/test_agent_llm_response_formatter.py api/tests/test_agent_orchestration_prompt_context.py` -> 12 passed.

### Phase R3: Agent Tools and Connectors
Status: `done`

#### Slice R3.1
Status: `done`
Targets:
- `api/services/agent/tools/research_tools.py` (1736) -> done (`api/services/agent/tools/research_tools.py` now 59 LOC with stream-stage decomposition)
- `api/services/agent/tools/web_extract_tools.py` (646) -> done (`api/services/agent/tools/web_extract_tools.py` now 465 LOC with extracted support helpers)
- `api/services/agent/connectors/browser_connector.py` (1056) -> done (`api/services/agent/connectors/browser_connector.py` now 465 LOC with staged browser flow helpers)
Acceptance:
- targeted tests for research/browser toolchain in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_agent_step_planner_research_and_logging.py`
Validation:
- Added staged helper modules for research and browser execution:
  - `api/services/agent/tools/research_web_tool_stream.py`
  - `api/services/agent/tools/research_web_stream_brave.py`
  - `api/services/agent/tools/research_web_stream_bing.py`
  - `api/services/agent/tools/research_web_stream_enrichment.py`
  - `api/services/agent/connectors/browser_stream_stage_initial.py`
  - `api/services/agent/connectors/browser_stream_stage_pages.py`
  - `api/services/agent/connectors/browser_stealth_script.py`
- Acceptance passed: 20 passed (`PYTHONPATH=. pytest -q api/tests/test_research_tool.py api/tests/test_web_extract_tool.py api/tests/test_browser_tools.py api/tests/test_tool_registry.py api/tests/test_tool_registry_specialist_capabilities.py`).
- Regression passed: 26 passed (`PYTHONPATH=. pytest -q api/tests/test_agent_step_planner_research_and_logging.py`).

#### Slice R3.2
Status: `done`
Targets:
- `api/services/agent/tools/document_highlight_tools.py` (824) -> done (`api/services/agent/tools/document_highlight_tools.py` now 431 LOC)
- `api/services/agent/tools/browser_tools.py` (616) -> done (`api/services/agent/tools/browser_tools.py` now 184 LOC)
- `api/services/agent/llm_execution_support_parts/polishing.py` (550) -> done (`api/services/agent/llm_execution_support_parts/polishing.py` now 490 LOC)
Acceptance:
- targeted tests for document/browser rendering contracts in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_chat_citations.py api/tests/test_agent_step_planner_research_and_logging.py`
Validation:
- Added extracted helper modules:
  - `api/services/agent/tools/browser_inspect_stream.py`
  - `api/services/agent/tools/document_highlight_helpers.py`
  - `api/services/agent/llm_execution_support_parts/polishing_text_utils.py`
- Acceptance/regression passed: 78 passed (`PYTHONPATH=. pytest -q api/tests/test_browser_tools.py api/tests/test_chat_citations.py api/tests/test_agent_step_planner_research_and_logging.py`).

#### Slice R3.3
Status: `done`
Targets:
- `api/services/agent/tools/gmail_tools.py` (806) -> done (`api/services/agent/tools/gmail_tools.py` now 373 LOC)
- `api/services/agent/tools/data_tools.py` (781) -> done (`api/services/agent/tools/data_tools.py` now 376 LOC)
- `api/services/agent/tools/business_workflow_tools.py` (514) -> done (`api/services/agent/tools/business_workflow_tools.py` now 360 LOC)
- `api/services/agent/tools/data_science/visualization_tool.py` (537) -> done (`api/services/agent/tools/data_science/visualization_tool.py` now 48 LOC)
Acceptance:
- targeted tests for mail/data/business tools in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests/test_agent_planner.py api/tests/test_agent_step_planner_research_and_logging.py`
Validation:
- Added extracted helper modules:
  - `api/services/agent/tools/gmail_tools_helpers.py`
  - `api/services/agent/tools/gmail_draft_tool.py`
  - `api/services/agent/tools/data_tools_helpers.py`
  - `api/services/agent/tools/data_science/visualization_execute.py`
  - `api/services/agent/tools/business_cloud_incident_digest_tool.py`
- Acceptance/regression passed: 71 passed (`PYTHONPATH=. pytest -q api/tests/test_gmail_tools_playwright.py api/tests/test_gmail_tools_report_flow.py api/tests/test_business_workflow_tools.py api/tests/test_tool_registry.py api/tests/test_tool_registry_specialist_capabilities.py api/tests/test_agent_planner.py api/tests/test_agent_step_planner_research_and_logging.py`).

### Phase R4: Upload, Ingestion, Routers, and Service Splits
Status: `done`

#### Slice R4.1
Status: `done`
Targets:
- `api/services/upload/indexing.py` (1647)
- `api/services/upload/groups.py` (589) -> done (`api/services/upload/groups.py` now 499 LOC)
Acceptance:
- upload/indexing targeted tests in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests`
Validation:
- Acceptance passed: 20 passed (`api/tests/test_upload_indexing.py`, `api/tests/test_upload_url_delete.py`, `api/tests/test_upload_streaming.py`).
- Regression passed: 731 passed (`PYTHONPATH=.:libs/ktem:libs/maia pytest -q api/tests`).

#### Slice R4.2
Status: `done`
Targets:
- `api/routers/uploads.py` (612) -> done (`api/routers/uploads.py` now 452 LOC with compatibility wrappers)
- `api/routers/web_preview.py` (901)
- `api/services/ingestion/manager.py` (979)
Acceptance:
- router and preview targeted tests in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests`
Validation:
- `api/routers/web_preview.py` refactored with helper modules and reduced to 478 LOC.
- `api/services/ingestion/manager.py` refactored with helper modules and reduced to 495 LOC.
- Acceptance passed: 31 passed (`api/tests/test_web_preview.py`, upload suite, `api/tests/test_ollama_index_migration.py`).
- Regression passed: 731 passed (`PYTHONPATH=.:libs/ktem:libs/maia pytest -q api/tests`).

#### Slice R4.3
Status: `done`
Targets:
- `api/services/mindmap_service.py` (606) -> done (`api/services/mindmap_service.py` now 427 LOC)
- `api/services/google/auth.py` (704) -> done (`api/services/google/auth.py` now 456 LOC with callback-compatible wrapper layer)
- `api/routers/integrations_api/ollama.py` (541) -> done (`api/routers/integrations_api/ollama.py` now 496 LOC with shared support helpers)
Acceptance:
- targeted service integration tests in this slice
Regression:
- `PYTHONPATH=. pytest -q api/tests`

### Phase R5: Frontend Chat and Shell Decomposition
Status: `done`

#### Slice R5.1
Status: `done`
Targets:
- `frontend/user_interface/src/app/components/ChatSidebar.tsx` (2205)
Acceptance:
- `npx vitest run ChatSidebar --passWithNoTests`
Regression:
- `npm test && npm run build`
Validation:
- `frontend/user_interface/src/app/components/ChatSidebar.tsx` refactored to 462 LOC with extracted `chatSidebar/` modules.
- Acceptance passed (no matching targeted tests): `No test files found, exiting with code 0`.
- Regression passed: 24 files / 69 tests.
- Build passed: `vite build` successful.

#### Slice R5.2
Status: `done`
Targets:
- `frontend/user_interface/src/app/components/chatMain/TurnsPanel.tsx` (759)
- `frontend/user_interface/src/app/components/chatMain/ComposerPanel.tsx` (658)
- `frontend/user_interface/src/app/components/chatMain/useChatMainInteractions.ts` (704)
Acceptance:
- `npm test -- chatMain`
Regression:
- `npm test && npm run build`
Validation:
- `TurnsPanel.tsx` reduced to 162 LOC with `chatMain/turns/*` modules.
- `ComposerPanel.tsx` reduced to 300 LOC with `chatMain/composer/*` modules.
- `useChatMainInteractions.ts` reduced to 424 LOC with `chatMain/interactions/*` modules.
- Acceptance passed: 2 files / 3 tests (`chatMain` filter).
- Regression passed: 24 files / 69 tests.
- Build passed: `vite build` successful.

#### Slice R5.3
Status: `done`
Targets:
- `frontend/user_interface/src/app/appShell/useConversationChat.ts` (884)
- `frontend/user_interface/src/app/appShell/useFileLibrary.ts` (618)
- `frontend/user_interface/src/app/appShell/app.tsx` (541)
Acceptance:
- `npx vitest run appShell --passWithNoTests`
Regression:
- `npm test && npm run build`
Validation:
- `useConversationChat.ts` reduced to 471 LOC with `appShell/conversationChat/*` orchestration helpers.
- `useFileLibrary.ts` reduced to 453 LOC with extracted job fallback logic in `fileLibraryJobCreation.ts`.
- `app.tsx` reduced to 469 LOC with `workspaceHelpers.tsx` extraction.
- Acceptance passed (no matching targeted tests): `No test files found, exiting with code 0`.
- Regression passed: 24 files / 69 tests.
- Build passed: `vite build` successful.

### Phase R6: Frontend Verification and Settings Decomposition
Status: `done`

#### Slice R6.1
Status: `done`
Targets:
- `frontend/user_interface/src/app/components/PdfEvidenceMap.tsx` (1410)
- `frontend/user_interface/src/app/components/mindmapViewer/MindMapViewer.tsx` (572)
Acceptance:
- mindmap/evidence targeted tests in this slice
Regression:
- `npm test`
Validation:
- `PdfEvidenceMap.tsx` reduced to 456 LOC with extracted `pdfEvidenceMap/edgeTypes.tsx` and graph render decomposition.
- `pdfEvidenceMap/buildGraph.ts` reduced to 436 LOC by moving render/layout assembly into `pdfEvidenceMap/buildGraphRender.ts`.
- `MindMapViewer.tsx` remains 448 LOC with extracted `mindmapViewer/viewerGraph.tsx`.
- Acceptance passed: 1 file / 3 tests (`mindmapViewer` targeted run).
- Regression passed: 24 files / 69 tests.

#### Slice R6.2
Status: `done`
Targets:
- `frontend/user_interface/src/app/components/settings/tabs/IntegrationsSettings.tsx` (1023)
- `frontend/user_interface/src/app/components/settings/useSettingsController.ts` (509)
- `frontend/user_interface/src/app/components/filesView/useFilesViewActions.ts` (521)
Acceptance:
- settings/files targeted tests in this slice
Regression:
- `npm test`
Validation:
- `IntegrationsSettings.tsx` reduced to 463 LOC with extracted `settings/tabs/integrations/*` modules.
- `useSettingsController.ts` reduced to 462 LOC with extracted key action helpers in `useSettingsControllerKeyActions.ts`.
- `useFilesViewActions.ts` reduced to 402 LOC with extracted upload/url actions in `filesView/uploadActions.ts`.
- Acceptance passed: 1 file / 2 tests (`settings` + `filesView` targeted run).
- Regression passed: 24 files / 69 tests.

#### Slice R6.3
Status: `done`
Targets:
- `frontend/user_interface/src/app/components/agentActivityPanel/app.tsx` (763)
- `frontend/user_interface/src/app/components/agentActivityPanel/useAgentActivityDerived.ts` (505)
- `frontend/user_interface/src/styles/theme.css` (806)
Acceptance:
- activity panel/theatre targeted tests in this slice
Regression:
- `npm test && npm run build`
Validation:
- `agentActivityPanel/app.tsx` reduced to 498 LOC with extracted `ActivityHeader.tsx`, `CinemaOverlay.tsx`, `ActivityPanelBody.tsx`, and navigation hooks.
- `agentActivityPanel/useAgentActivityDerived.ts` reduced to 477 LOC with extracted derive helpers.
- `styles/theme.css` reduced to 263 LOC with split style modules in `styles/theme/assistant_answer.css` and `styles/theme/citation_composer.css`.
- Acceptance passed: 6 files / 23 tests (`agentActivityPanel` + `agentDesktopScene` targeted run).
- Regression passed: 24 files / 69 tests.
- Build passed: `vite build` successful.

### Phase R7: Library Module Decomposition
Status: `done`

#### Slice R7.1
Status: `done`
Targets:
- `libs/maia/maia/indices/qa/citation_qa.py` (550)
- `libs/ktem/ktem/reasoning/rewoo.py` (503)
- `libs/ktem/ktem/pages/chat/chat_page/events.py` (522)
Acceptance:
- library targeted tests in this slice
Regression:
- `PYTHONPATH=. pytest -q libs`
Validation:
- `libs/maia/maia/indices/qa/citation_qa.py` reduced to 500 LOC with extracted citation strength module (`citation_strength.py`).
- `libs/ktem/ktem/reasoning/rewoo.py` reduced to 499 LOC.
- `libs/ktem/ktem/pages/chat/chat_page/events.py` reduced to 499 LOC.
- Acceptance passed: 5 tests (`PYTHONPATH=.:libs/maia:libs/ktem pytest -q libs/maia/tests/test_inline_citation_numbering.py libs/ktem/ktem_tests/test_qa.py`).
- Regression passed: 92 passed, 23 skipped (`PYTHONPATH=.:libs/maia:libs/ktem pytest -q libs`).

#### Slice R7.2
Status: `done`
Targets:
- `libs/ktem/ktem/index/file/graph/lightrag_pipelines.py` (550)
- `libs/ktem/ktem/index/file/graph/nano_pipelines.py` (549)
- `libs/ktem/ktem/index/file/file_ui/file_index_events.py` (517)
Acceptance:
- graph/index targeted tests in this slice
Regression:
- `PYTHONPATH=. pytest -q libs`
Validation:
- `lightrag_pipelines.py` reduced to 393 LOC by extracting shared GraphRAG utility logic into `graph/graphrag_shared.py`.
- `nano_pipelines.py` reduced to 395 LOC using the same shared GraphRAG utility layer.
- `file_index_events.py` reduced to 449 LOC by extracting event wiring helpers into `file_ui/event_helpers.py`.
- Acceptance passed: 3 passed (`PYTHONPATH=.:libs/maia:libs/ktem pytest -q libs/ktem/ktem_tests/test_qa.py libs/maia/tests/test_indexing_retrieval.py`).
- Regression passed: 92 passed, 23 skipped (`PYTHONPATH=.:libs/maia:libs/ktem pytest -q libs`).

### Phase R8: Final Full-System Verification and Cleanup
Status: `done`

#### Slice R8.1
Status: `done`
Targets:
- verify all previously oversized source files are `<500 LOC`
- remove resolved entries from [files_over_500_loc.md](/Users/disanssebowabasalidde/Documents/GitHub/maia/docs/files_over_500_loc.md)
Acceptance:
- `git ls-files -z | xargs -0 wc -l | awk '$2 != "total" && $1 > 500 && $2 !~ /(^|\\/)tests?\\// && $2 !~ /(^|\\/)test_/ && $2 ~ /\\.(py|ts|tsx|js|jsx|css|scss|html|htm|sql|sh|bash|zsh|yaml|yml|toml|ini|cfg|conf|go|rs|java|kt|swift|rb|php|c|cc|cpp|h|hpp)$/'` returns empty
Regression:
- `PYTHONPATH=. pytest -q`
- `npm test`
- `npm run build`
Progress:
- Full backend regression passed: `823 passed, 23 skipped` (`PYTHONPATH=. pytest -q`).
- Frontend regression passed:
  - `npm test` -> `24 files / 69 tests passed`
  - `npm run build` -> successful Vite production build.
- Refactored `libs/ktem/ktem/assets/css/main.css` into ordered imported modules under:
  - `libs/ktem/ktem/assets/css/main/`
- `main.css` is now an import facade (10 LOC); all split CSS modules are under 500 LOC.
- Updated [files_over_500_loc.md](/Users/disanssebowabasalidde/Documents/GitHub/maia/docs/files_over_500_loc.md) to zero remaining source files over 500 LOC.
- Acceptance passed: source LOC scan for tracked code files returns empty (>500 filter).
- Final full-system regression re-run after CSS split:
  - `PYTHONPATH=. pytest -q` -> `823 passed, 23 skipped`
  - `npm test` -> `24 files / 69 tests passed`
  - `npm run build` -> successful Vite production build
