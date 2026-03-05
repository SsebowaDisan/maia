# Agent Results and Performance Improvements

## Why this exists

This note captures:

1. The concrete failure pattern observed in a recent run.
2. Immediate code-level mitigations now implemented.
3. A research-backed roadmap for improving result quality, latency, and reliability.

## Failure pattern observed

For a simple query ("what is machine learning"), the agent:

- Generated synthetic keywords (for example, `what_4`, `what_5`).
- Added unnecessary steps (`workspace.sheets.track_step`, `documents.highlight.extract`).
- Failed early on Google Sheets auth (`401 invalid authentication credentials`).
- Returned process-heavy output with weak user-value.

## Implemented fixes (code)

### 1) Removed synthetic keyword fabrication

- File: `api/services/agent/llm_research_blueprint.py`
- Removed numbered fallback generation (`base_4`, `base_5`, ...).
- Added stopword/noise filtering and placeholder suppression.
- Added phrase expansion without fake tokens.

### 2) Scaled keyword depth to task complexity

- File: `api/services/agent/orchestration/step_planner_sections/research.py`
- Added adaptive keyword floor:
  - Simple short question -> lower keyword floor.
  - True research requests -> higher keyword floor.

### 3) Stopped unconditional highlight extraction

- File: `api/services/agent/orchestration/step_planner_sections/research.py`
- `documents.highlight.extract` is now auto-inserted only when:
  - user explicitly asks for highlight extraction, or
  - file context + file-specific language is present.

### 4) Made workspace roadmap logging configurable for company mode

- File: `api/services/agent/orchestration/step_planner_sections/workspace_logging.py`
- Company mode now enables Sheets/Docs roadmap logging by default (theatre-first behavior).
- It can be disabled with `agent.company_agent_always_workspace_logging: false`.

### 5) Reduced unnecessary web actions for non-web tasks

- File: `api/services/agent/planner.py`
- If routing mode is `none` and no explicit web intent exists, web steps are pruned.
- Preserves URL-based web steps when a concrete URL exists in step params.
- Adds safe `report.generate` fallback if pruning empties the plan.

### 6) Improved planner prompts to avoid irrelevant roadmap steps

- Files:
  - `api/services/agent/llm_planner.py`
  - `api/services/agent/llm_plan_optimizer.py`
- Updated prompt instructions to keep workspace roadmap tools conditional.

### 7) Improved direct-answer quality for question-style prompts

- File: `api/services/agent/tools/data_tools.py`
- `report.generate` now attempts direct-answer synthesis for clear question prompts
  when no browser evidence exists.

### 8) Suppressed research blueprint section when no research tools are planned

- File: `api/services/agent/orchestration/answer_builder_sections/plan.py`
- Avoids showing research term/keyword noise in non-research runs.

## Added tests

- `api/tests/test_agent_llm_research_blueprint.py`
  - No placeholder keyword regression coverage.
- `api/tests/test_agent_step_planner_research_and_logging.py`
  - Workspace logging default behavior and highlight insertion gates.
- `api/tests/test_agent_planner.py`
  - Simple query avoids `marketing.web_research`.
  - Explicit online-search query keeps web step.
- `api/tests/test_agent_answer_builder_plan_section.py`
  - Research blueprint visibility is now tied to actual research steps.

## What Codex, ChatGPT Agent, and Cursor do well

### Codex (OpenAI)

- Runs tasks in isolated cloud sandboxes and supports parallel tasks in separate environments.
- Lets users provide repository-level guidance via `AGENTS.md`.
- Surfaces verifiable actions with terminal logs and citations for review.
- Supports configurable network access policies for agent containers.

Sources:
- https://openai.com/index/introducing-codex/
- https://platform.openai.com/docs/codex
- https://platform.openai.com/docs/codex/agent-network

### ChatGPT Agent (OpenAI)

- Unifies web interaction, terminal/code execution, connectors, and file synthesis in one flow.
- Uses explicit user approval gates for consequential actions.
- Exposes execution visibility with an on-screen narration/activity stream.

Sources:
- https://openai.com/index/introducing-chatgpt-agent/
- https://help.openai.com/en/articles/11752874-chatgpt-agent

### Cursor Agent

- Supports clear execution modes (manual/auto) to control autonomy.
- Uses checkpoints and restore workflows to recover from bad edits.
- Uses persistent `Rules` and `Memories` so behavior remains consistent across runs.
- Supports subagents and reusable skills to keep complex workflows modular.

Sources:
- https://docs.cursor.com/en/agent/modes
- https://docs.cursor.com/en/agent/checkpoints
- https://docs.cursor.com/en/context/rules
- https://docs.cursor.com/en/context/memories
- https://cursor.com/changelog
- https://cursor.com/blog/agent

## Inferred design pattern (from sources above)

Across these systems, the most reliable structure is:

1. Plan visibility first (users can see intended steps before execution).
2. Observable execution (live stream of each tool/event).
3. Reversible execution (checkpoint/restore and explicit approvals).
4. Persistent behavior memory (rules + run history + eval feedback).

## Research-backed roadmap

## 1) Build an eval flywheel around traces (highest ROI)

Use trace-level evals and graders to prevent regressions and catch orchestration errors early.

Sources:
- OpenAI trace grading guide: https://platform.openai.com/docs/guides/trace-grading
- OpenAI agent evals guide: https://platform.openai.com/docs/guides/agent-evals

## 2) Keep architecture simple until evidence justifies complexity

Prefer simple composable workflows over deeply layered abstractions unless metrics prove gains.

Source:
- Anthropic "Building effective agents" (Dec 19, 2024): https://www.anthropic.com/engineering/building-effective-agents

## 3) Improve planning quality with explicit pre-act planning for hard tasks

Adopt stronger multi-step planning only for tasks that need it (e.g., deep research, multi-tool tasks),
not for short direct questions.

Source:
- Pre-Act (2025): https://arxiv.org/abs/2505.09970

## 4) Add explicit reflection loops for repeated failure classes

Use lightweight reflection memory after failures (tool auth failures, empty evidence, contradiction flags)
to reduce repeated mistakes.

Source:
- Reflexion: https://arxiv.org/abs/2303.11366

## 5) Track capability-specific benchmarks and safety gates

Measure long-horizon reasoning, tool-use robustness, and safety behavior with benchmark suites.

Sources:
- AgentBench: https://arxiv.org/abs/2308.03688
- LifelongAgentBench: https://arxiv.org/abs/2505.11942
- Agent-SafetyBench: https://arxiv.org/abs/2412.14470

## Suggested production KPIs

- `% runs with direct answer to user ask` (first section answers question directly)
- `% runs with at least one grounded source for research tasks`
- `% runs with irrelevant tool calls` (should trend down)
- `tool failure rate by connector` (Sheets, Docs, Web, Browser)
- `median steps per intent class` (simple QA should be minimal)
- `p50/p95 latency` and `token cost per successful run`
- `eval pass rate` on stable trace-grading suites
