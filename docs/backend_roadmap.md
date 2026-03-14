# Maia Agent OS — Backend Engineering Roadmap

## Principles
1. One phase completes before the next begins.
2. Each slice has a concrete acceptance test — no slice ships without it.
3. No file exceeds 500 LOC. One file = one responsibility.
4. Every feature must work end-to-end before moving on — no stub layers.
5. Existing Maia code is extended, not replaced.
6. Connectors are first-class citizens, not plugins bolted on later.
7. Computer Use is a native capability, not an add-on — agents see and act on screens.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                │
│  Chat UI · Agent Builder · Marketplace · Connector Config       │
│  Activity Theatre · Computer Use Live View · Approval Gates     │
└─────────────────────────────────────────────────────────────────┘
                             ↕  REST + SSE
┌─────────────────────────────────────────────────────────────────┐
│                      API GATEWAY LAYER                          │
│  Auth · Tenant Routing · Rate Limiting · Usage Metering         │
└─────────────────────────────────────────────────────────────────┘
                             ↕
┌───────────────┬──────────────────┬─────────────────────────────┐
│ AGENT RUNTIME │  CONNECTOR BUS   │   MARKETPLACE ENGINE        │
│ Scheduler     │  Tool Registry   │   Registry · Versioning     │
│ Orchestrator  │  OAuth Manager   │   Publishing · Billing      │
│ Gate Engine   │  Credential Vault│   Discovery · Reviews       │
│ Memory Store  │  Computer Use    │   Installation Pipeline     │
│ Workflow DAG  │  Browser Session │                             │
└───────────────┴──────────────────┴─────────────────────────────┘
                             ↕
┌─────────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                         │
│  LLM Providers · Vector Stores · Postgres · Redis · Playwright  │
│  (existing Maia foundation)                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Status Legend
- `done` — implemented and acceptance test passing
- `in_progress` — active work
- `todo` — not started
- `blocked` — waiting on prerequisite

---

## Phase 0 — Foundation Schemas
**Goal:** Stabilise the data contracts that every other phase depends on. No new features, only hardening and schema work.

### B0-01 — Agent definition schema ✅ `done`
- **Files:** `api/schemas/agent_definition/` (6 files)
- **Implemented:** `MemoryConfig`, `TriggerConfig`, `GateConfig`, `OutputConfig`, `AgentDefinitionSchema`
- **Acceptance:** Schema validates, serialises to JSON, rejects missing required fields.

### B0-02 — Tenant model + store + router ✅ `done`
- **Files:** `api/models/tenant.py`, `api/services/tenants/store.py`, `api/routers/tenants.py`
- **Implemented:** `Tenant` SQLModel, full CRUD, member management, soft-delete.
- **Acceptance:** Create/read/update/deactivate tenant via REST. Member add/remove works.

### B0-03 — Connector definition schema ✅ `done`
- **Files:** `api/schemas/connector_definition/` (4 files)
- **Implemented:** `AuthConfig` (all 5 strategies), `ToolSchema` with LLM function spec, `ConnectorDefinitionSchema`
- **Acceptance:** Schema validates all auth types. `to_llm_function_spec()` produces OpenAI-compatible output.

### B0-04 — Agent definition store + router ✅ `done`
- **Files:** `api/models/agent_definition.py`, `api/services/agent_definitions/store.py`, `api/routers/agent_definitions.py`
- **Implemented:** SQLModel record, CRUD store, full REST router, marketplace listing endpoint.
- **Acceptance:** Create, version, retrieve, soft-delete agent definitions. Marketplace catalog endpoint works.

---

## Phase 1 — Connector Infrastructure + Computer Use Runtime ✅ `done`
**Goal:** Build the connector layer first because agents depend on it. Also add Computer Use as a native agent capability — the ability for agents to see and control a browser like a human.

### B1-01 — Connector registry ✅ `done`
- **File:** `api/services/connectors/registry.py`
- **Task:** In-memory + database-backed registry. `register_connector(definition)`, `get_connector(connector_id)`, `list_connectors()`. Seed with built-in stubs: `google_workspace`, `microsoft_365`, `salesforce`, `hubspot`, `slack`, `notion`, `jira`, `github`, `postgres_query`, `http_request`.
- **Acceptance:** `GET /api/connectors` returns all registered connectors with their full definitions.

### B1-02 — Credential vault
- **File:** `api/services/connectors/vault.py`
- **Task:** Encrypted credential store per tenant per connector. `store_credential(tenant_id, connector_id, credentials)`, `get_credential(tenant_id, connector_id)`, `revoke_credential(tenant_id, connector_id)`. Fernet encryption with per-tenant key derived from master secret. Never log credentials — vault methods raise `VaultAccessError` if called outside the execution context.
- **Acceptance:** Store and retrieve OAuth tokens and API keys. Confirm ciphertext in DB column. Plaintext never appears in logs.

### B1-03 — OAuth2 PKCE flow
- **File:** `api/services/connectors/oauth.py`
- **Task:** Generic OAuth2 PKCE flow. `build_auth_url(connector_id, tenant_id, redirect_uri)` → authorization URL with PKCE challenge and CSRF state token. `exchange_code(connector_id, tenant_id, code, state)` → validates state, exchanges code, stores tokens via vault. `refresh_token(connector_id, tenant_id)` → refreshes and re-stores. Routes: `GET /api/connectors/:connector_id/oauth/start`, `GET /api/connectors/oauth/callback`.
- **Acceptance:** Full OAuth2 round-trip with Google (real test). Token stored, PKCE state validated, refresh works on expiry.

### B1-04 — API key connector flow
- **File:** `api/routers/connectors.py`
- **Task:** `POST /api/connectors/:connector_id/credentials` — accepts `{api_key}` or `{username, password}`, validates by making a test call to the connector's `test_connection_url`, stores in vault if valid. Returns `{status, latency_ms}`.
- **Acceptance:** API key accepted after live test ping, rejected on bad key with a readable error.

### B1-05 — Tool execution engine
- **File:** `api/services/connectors/tool_executor.py`
- **Task:** `execute_tool(tool_id, tenant_id, params: dict) → ToolResult`. Resolves tool → connector → credentials from vault → HTTP call. Enforces 30s timeout. Returns `{success, data, error, latency_ms}`. Implements `ToolHandler` interface: `handle(params, credentials) -> dict`. All built-in tools implement this interface.
- **Acceptance:** `google_drive.read_file` executes with a live Google credential and returns file content within 30s.

### B1-06 — Built-in tool implementations (batch 1)
- **Files:** `api/services/connectors/tools/` — one file per connector
- **Connectors:**
  - `google_workspace.py` — `gmail.send`, `gmail.read`, `gdrive.read_file`, `gdrive.write_file`, `gcalendar.create_event`, `gcalendar.list_events`
  - `microsoft_365.py` — `outlook.send`, `outlook.read`, `onedrive.read_file`, `teams.send_message`
  - `slack.py` — `slack.send_message`, `slack.read_channel`, `slack.list_channels`
  - `notion.py` — `notion.read_page`, `notion.create_page`, `notion.update_page`
  - `http_request.py` — `http.get`, `http.post` (generic, for custom APIs)
- **Acceptance:** Each tool has a unit test with a mocked HTTP layer. Schema generates valid LLM function spec.

### B1-07 — Connector health and test endpoint
- **File:** `api/routers/connectors.py`
- **Task:** `POST /api/connectors/:connector_id/test` — executes a read-only test call using stored credentials. Returns `{status: "ok" | "error", latency_ms, detail}`. Separate from the credential-submission test — this re-tests an already-connected connector.
- **Acceptance:** Returns `ok` for live connected Google account. Returns `error` with readable message for expired token. Correctly distinguishes auth errors from network errors.

### B1-08 — Connector binding to tenant
- **File:** `api/services/connectors/bindings.py`
- **Task:** `ConnectorBinding` links a connector to a tenant with scoped credentials and agent permissions. `bind_connector(tenant_id, connector_id, allowed_agent_ids)`, `get_bindings(tenant_id)`, `is_tool_allowed(tenant_id, agent_id, tool_id)`. An agent not in `allowed_agent_ids` calling a tool raises `ToolPermissionError`.
- **Acceptance:** Agent not in `allowed_agent_ids` cannot call that connector's tools — returns a permission error. Changing bindings takes effect on next tool call.

---

### Computer Use Block (B1-CU)
**Goal:** Give every Maia agent the ability to see and control a browser — the same loop as Claude Computer Use and OpenClaw. Every action the agent takes is visible live in the frontend BrowserScene.

The loop:
```
task → open browser → screenshot → Claude computer_20251124 tool →
  action (click / type / scroll / key / navigate) →
    screenshot → Claude → action → ... → done
```

### B1-CU-01 — Browser session manager
- **File:** `api/services/computer_use/browser_session.py`
- **Task:** Manages a single Playwright Chromium session per Computer Use run. `open(url)` launches headless browser and navigates to the starting URL. `screenshot() → str` captures viewport as base64 PNG. `close()`. Session is tied to a `session_id`. Viewport fixed at 1280×800. Each session is isolated — separate browser context.
- **Acceptance:** Session opens a URL, `screenshot()` returns a valid base64 PNG, `close()` releases all Playwright resources. Two concurrent sessions do not interfere.

### B1-CU-02 — Action executor
- **File:** `api/services/computer_use/action_executor.py`
- **Task:** Translates Claude `computer_20251124` tool call inputs into Playwright page actions. Handles all action types:
  - `screenshot` → capture viewport, return base64 PNG
  - `left_click`, `right_click`, `double_click`, `triple_click` at `coordinate: [x, y]`
  - `type` → `page.keyboard.type(text)`
  - `key` → `page.keyboard.press(key)` (supports combos: `ctrl+s`, `cmd+t`)
  - `scroll` → `page.mouse.wheel(dx, dy)` at coordinate
  - `mouse_move` → `page.mouse.move(x, y)`
  - `left_click_drag` → mouse down, move, mouse up
  - `navigate` → `page.goto(url)` (Maia extension beyond standard Computer Use)
  - `wait` → `asyncio.sleep(seconds)`
  - `zoom` → crop screenshot to region, return at full resolution
- **Acceptance:** All 10 action types execute without error. Invalid coordinates are clamped to viewport bounds. `navigate` works with absolute URLs. Each action returns `{success, error, screenshot_b64}`.

### B1-CU-03 — Computer Use agent loop
- **File:** `api/services/computer_use/agent_loop.py`
- **Task:** The core loop that drives a browser using the Anthropic API with Computer Use beta. `run_computer_use_task(task, start_url, session_id, max_steps, on_event)` where `on_event` is a callback yielding `ComputerUseEvent` objects.

  Loop:
  1. Take a screenshot of the current browser state.
  2. Call Anthropic API (`claude-sonnet-4-6`) with `computer_20251124` tool, display dimensions (1280×800), and the screenshot as a `image/png` base64 block.
  3. Receive response — if `stop_reason == "tool_use"`, extract the tool call.
  4. Execute the action via `ActionExecutor`.
  5. Emit `ComputerUseEvent(type="action", action=..., screenshot_b64=...)` via `on_event`.
  6. If Claude returns text without a tool call → task complete. Emit `ComputerUseEvent(type="done", result=text)`.
  7. Enforce `max_steps` limit. Emit `ComputerUseEvent(type="limit_reached")` if exceeded.

  Uses `anthropic` SDK directly with `betas=["computer-use-2025-11-24"]`. API key read from env `ANTHROPIC_API_KEY`.
- **Acceptance:** Agent given the task "Go to google.com and search for Maia AI" completes the task in ≤ 8 steps. Each step emits a screenshot event. `max_steps` blocks infinite loops.

### B1-CU-04 — Session registry
- **File:** `api/services/computer_use/session_registry.py`
- **Task:** In-memory thread-safe registry of active Computer Use sessions. `create_session(tenant_id, task, start_url) → session_id`. `get_session(session_id) → SessionState`. `cancel_session(session_id)`. `list_active_sessions(tenant_id)`. `SessionState` holds: `session_id`, `tenant_id`, `status` (`running | done | cancelled | error`), `task`, `step_count`, `event_queue: asyncio.Queue`, `started_at`, `result`.

  The agent loop runs in a background `asyncio.Task`. Events are pushed into the `event_queue` which the SSE endpoint consumes.
- **Acceptance:** Creating a session returns a unique ID. Cancelling mid-run sets status to `cancelled` and stops the loop. Two concurrent sessions run independently.

### B1-CU-05 — Computer Use router
- **File:** `api/routers/computer_use.py`
- **Task:** REST + SSE endpoints for Computer Use sessions.
  - `POST /api/computer-use/sessions` — `{task, start_url, max_steps?}` → `{session_id}`. Creates session, starts loop in background.
  - `GET /api/computer-use/sessions/{session_id}/stream` — SSE endpoint. Streams `ComputerUseEvent` objects as JSON. Each event includes: `type`, `action` (if applicable), `screenshot_b64` (latest browser state), `step`, `timestamp`. Closes stream when `done`, `cancelled`, or `error` event received.
  - `DELETE /api/computer-use/sessions/{session_id}` — cancels the session.
  - `GET /api/computer-use/sessions` — list active sessions for the current tenant.
- **Acceptance:** Full round-trip: `POST` starts session, SSE stream receives screenshot events in real time, `DELETE` cancels mid-run. Frontend BrowserScene can consume the screenshot stream directly.

### B1-CU-06 — Computer Use as an agent tool
- **File:** `api/services/connectors/tools/computer_use_tool.py`
- **Task:** Wrap the Computer Use agent loop as a first-class connector tool so any Maia agent can invoke it. Tool: `computer.browse_and_act(task: str, start_url: str, max_steps: int)` → `{result, steps_taken, final_screenshot_b64}`. Registered in the connector registry under connector id `computer_use`. The tool runs the full Computer Use loop internally and returns the text result. The live session stream is attached to the parent agent's `run_id` so the frontend can display it in the BrowserScene during any agent run.
- **Acceptance:** An agent with `computer_use` in its `tools` list can invoke `computer.browse_and_act`. The result appears in the agent's output. The BrowserScene shows live screenshots during the sub-task.

---

## Phase 2 — Agent Runtime ✅ `done` ✅ `bugs fixed`

> **Bug fixes applied 2026-03-14:**
> - **BUG-01** (CRITICAL): `orchestrator.stream()` called in 5 files but the method does not exist. Fixed by creating `api/services/agents/runner.py` as a thin adapter around `AgentOrchestrator.run_stream()` and updating all callers.
> - **BUG-02** (CRITICAL): `schema.gate` (singular) used instead of `schema.gates` (list). Fixed in `api/routers/agents.py`; added `check_gates()` (list-aware) to `gate_engine.py`.
> - **BUG-03** (CRITICAL): `call_llm_json` imported from non-existent `api.services.agent.llm_runtime`. Fixed by creating `api/services/agents/llm_utils.py` and updating `resolver.py` + `improvement.py`.
> - **BUG-05** (HIGH): `trigger.connector_id` used in `event_triggers.py` and `scheduler.py` but field is `source_connector_id` on `OnEventTrigger`. Fixed in both files.
> - **BUG-06** (HIGH): `fallback == "fail"` string comparison against `GateFallbackAction` enum. Fixed to `GateFallbackAction.abort` in `gate_engine.py`.
> - **ISSUE-07** (MEDIUM): Missing `api/sdk/__init__.py`. Created.
> - **ISSUE-08** (MEDIUM): Memory TTL short-circuit expression in `agents.py` could return `0`. Fixed to direct attribute access.
> - **ISSUE-09** (MEDIUM): Dead `if False` branch in `agent_loop.py`. Removed.
> - **ISSUE-11** (MEDIUM): Telemetry `record_run_start/end` never called from agents router. Wired in.
> - **ISSUE-12** (MEDIUM): Budget check `assert_budget_ok` never called. Wired in at run start.
**Goal:** Build the core execution engine. Agents run against a definition, access permitted tools (including Computer Use), respect gates, remember past runs, and emit structured output.

### B2-01 — Agent definition store (versioned)
- **File:** `api/services/agents/definition_store.py`
- **Task:** CRUD for `AgentDefinitionSchema` per tenant with full version history. `create_agent(tenant_id, definition)`, `get_agent(tenant_id, agent_id, version?)`, `list_agents(tenant_id)`, `update_agent(...)` bumps version and archives the old one, `delete_agent(...)` soft-delete. Validate against schema on every write.
- **Acceptance:** Create, version, and retrieve agent definitions. `get_agent(..., version="1.0.0")` returns the correct historical snapshot.

### B2-02 — Agent resolver (message routing)
- **File:** `api/services/agents/resolver.py`
- **Task:** Given a user message and tenant context, determine which installed agent handles it. Strategy: (1) explicit `@agent-name` prefix, (2) LLM-based intent classification against installed agents' descriptions, (3) fallback to default agent or Maia's existing ask mode. Returns `AgentResolution: {agent_id, confidence, reasoning}`.
- **Acceptance:** `@proposal-writer draft a proposal for Acme` routes to the correct agent. Ambiguous query routes to the closest match by confidence score.

### B2-03 — Gate engine
- **File:** `api/services/agents/gate_engine.py`
- **Task:** Middleware that intercepts tool calls during execution. For each tool call, checks `agent.gates`: if a gate exists for that `tool_id`, pauses execution, emits `gate_pending` activity event with `{gate_id, tool_id, params_preview, cost_estimate}`, waits for `gate_approve` or `gate_reject` signal. `approve_gate(run_id, gate_id)` and `reject_gate(run_id, gate_id)` endpoints resume or cancel the run. Timeout falls back to `GateConfig.fallback_action`.
- **Acceptance:** Agent with a gate on `email_sender` pauses before sending, resumes only after API approval. Timeout with `fallback_action=skip` skips the tool call and continues.

### B2-04 — Memory layer
- **File:** `api/services/agents/memory.py`
- **Task:** Three memory tiers:
  - `WorkingMemory` — per-conversation key-value store in Redis, TTL from `MemoryConfig.working.ttl_seconds`.
  - `EpisodicMemory` — per-tenant per-agent timestamped log. `record_episode(tenant_id, agent_id, summary, outcome)`, `recall_episodes(tenant_id, agent_id, query, limit=5)` via vector similarity over episode summaries.
  - `SemanticMemory` — wraps existing RAG index. `recall_knowledge(tenant_id, query)` returns snippets from the company's document store.
- **Acceptance:** After 3 runs of the proposal agent, `recall_episodes` returns the 3 most relevant past proposals when given a new prospect name.

### B2-05 — Multi-agent orchestration
- **File:** `api/services/agents/orchestrator.py`
- **Task:** Extend the existing company_agent orchestrator to support agent delegation. Orchestrator calls `delegate_to_agent(agent_id, task, context)` which runs a sub-agent and returns its result. Enforces `max_delegation_depth` from the agent config. Each delegation emits `agent_delegated` activity events with `{parent_agent_id, child_agent_id, task}`.
- **Acceptance:** Orchestrator delegates a research sub-task to a web-researcher agent, receives the result, and includes it in the final answer. Depth > `max_delegation_depth` is blocked with a clear error.

### B2-06 — Agent execution endpoint
- **File:** `api/routers/agents.py`
- **Task:** `POST /api/agents/:agent_id/run` — starts a streaming agent run. Returns SSE stream of activity events + final result. Integrates gate engine, memory layer, tool executor, and Computer Use tool. Used by scheduled and event-triggered runs as well as direct invocation.
- **Acceptance:** Agent runs, emits activity events, writes episode to memory, returns structured blocks. Computer Use tool invocation streams screenshots to BrowserScene.

### B2-07 — Scheduled trigger engine
- **File:** `api/services/agents/scheduler.py`
- **Task:** Cron-based trigger runner. Reads agent definitions with `trigger.family == "scheduled"` for each tenant. Uses APScheduler. On trigger: creates a synthetic conversation, runs the agent, stores result, optionally sends a notification. `register_schedule(tenant_id, agent_id, cron_expr)`, `unregister_schedule(...)`.
- **Acceptance:** Agent with `trigger: {family: scheduled, cron_expression: "0 9 * * 1"}` runs every Monday at 9am and posts output to the conversation.

### B2-08 — Event trigger engine
- **File:** `api/services/agents/event_triggers.py`
- **Task:** Webhook receiver + internal event bus. `POST /api/webhooks/:tenant_id/:connector_id` receives external events. Maps event to any agent with a matching `trigger.on_event` pattern. Queues agent runs asynchronously. `subscribe_agent_to_event(tenant_id, agent_id, event_pattern)`.
- **Acceptance:** Salesforce webhook fires on deal stage change, triggers a deal-summary agent, result appears in conversation within 10 seconds.

---

## Phase 3 — Marketplace Backend ✅ `done`
**Goal:** Build the registry, publishing pipeline, and installation system that lets agents be packaged and distributed — including Computer Use agents.

### B3-01 — Marketplace agent registry
- **File:** `api/services/marketplace/registry.py`
- **Task:** Central registry of published agents. Separate from tenant-scoped definitions. `publish_agent(publisher_id, definition, metadata)`, `get_marketplace_agent(agent_id, version)`, `list_marketplace_agents(filters)`, `search_marketplace_agents(query)`. Each entry includes: `publisher_id`, `semver`, `tags`, `required_connectors`, `pricing_tier (free | paid | enterprise)`, `install_count`, `avg_rating`, `verified flag`. Computer Use agents are tagged `computer_use` and require the `computer_use` connector.
- **Acceptance:** Publish an agent, retrieve it, list all agents with filters by tag and required connector. Computer Use agent appears with correct tag.

### B3-02 — Publishing pipeline
- **File:** `api/services/marketplace/publisher.py`
- **Task:** Validate schema on publish. Automated safety checks: (1) no hardcoded credentials in system prompt, (2) declared tools match registry, (3) delegation depth ≤ 5, (4) `http_request` tool blocked for private IP ranges, (5) Computer Use agents must declare `max_steps ≤ 50`. Status flow: `pending_review → approved → published`. `submit_for_review(publisher_id, agent_id)`, `approve_agent(agent_id)` (admin only), `reject_agent(agent_id, reason)`.
- **Acceptance:** Agent with hardcoded password in system prompt is rejected. Computer Use agent with `max_steps=200` is rejected. Clean agent progresses to `pending_review`.

### B3-03 — Installation pipeline
- **File:** `api/services/marketplace/installer.py`
- **Task:** `install_agent(tenant_id, marketplace_agent_id, version, connector_mapping: dict)` — copies definition into tenant's agent store, binds declared tool IDs to tenant's installed connectors. Returns `{success, missing_connectors, agent_id}`. `uninstall_agent(tenant_id, agent_id)`. For Computer Use agents, checks that `ANTHROPIC_API_KEY` is configured for the tenant.
- **Acceptance:** Installing agent that requires `slack` when Slack is not connected returns `{success: false, missing_connectors: ["slack"]}`. Computer Use agent fails install if `ANTHROPIC_API_KEY` is missing.

### B3-04 — Versioning and update system
- **File:** `api/services/marketplace/versioning.py`
- **Task:** When a publisher releases a new version, tenants receive an `update_available` notification. `check_for_updates(tenant_id)` returns list of agents with newer versions. `update_agent(tenant_id, agent_id, target_version)` re-runs installation, migrating saved config. Tenants can pin to a version and opt out of auto-updates.
- **Acceptance:** Publisher releases v1.1.0. Tenant sees update badge. Updating migrates connector bindings without losing them.

### B3-05 — Usage metering
- **File:** `api/services/marketplace/metering.py`
- **Task:** Record per-agent per-tenant per-day: LLM token usage, tool call count, Computer Use step count, run duration. `record_usage(tenant_id, agent_id, run_id, tokens_in, tokens_out, tool_calls, computer_use_steps, duration_ms)`. `get_usage_summary(tenant_id, date_range)`. For paid agents, `calculate_charges(tenant_id, billing_period)`. Computer Use steps are metered separately (each step = 1 screenshot + 1 API call).
- **Acceptance:** After 10 runs, usage report shows correct token totals and Computer Use step counts per agent.

### B3-06 — Ratings and reviews
- **File:** `api/services/marketplace/reviews.py`
- **Task:** `submit_review(tenant_id, agent_id, rating: 1-5, review_text)`. One review per tenant per agent. `get_reviews(agent_id, limit, offset)`. `get_aggregate_rating(agent_id) → {avg, count, distribution}`. Publishers can respond. Flag/moderate endpoint for abuse.
- **Acceptance:** Two tenants submit reviews, aggregate rating correct, publisher response stored and visible.

### B3-07 — Marketplace search and discovery API
- **File:** `api/routers/marketplace.py`
- **Task:** `GET /api/marketplace/agents` with params: `q` (text search), `tags`, `required_connectors`, `pricing`, `has_computer_use` (boolean filter), `sort_by (installs | rating | newest)`, `page`, `limit`. Full-text search via Postgres tsvector. `GET /api/marketplace/agents/:agent_id` returns full detail including reviews and publisher info.
- **Acceptance:** Searching "CRM proposal" returns agents tagged `crm` or `sales`. `has_computer_use=true` returns only Computer Use agents. Sorting by rating works correctly.

---

## Phase 4 — Advanced Connector Ecosystem ✅ `done`
**Goal:** Expand the connector library, add the connector SDK for third-party developers, and support bidirectional data flows.

### B4-01 — CRM connectors (batch 2)
- **Files:** `api/services/connectors/tools/salesforce.py`, `hubspot.py`, `pipedrive.py`
- **Tools:**
  - `salesforce` — `crm.get_contact`, `crm.get_deal`, `crm.update_deal`, `crm.create_task`, `crm.list_deals_by_stage`
  - `hubspot` — `crm.get_contact`, `crm.get_deal`, `crm.create_note`, `crm.list_pipeline`
  - `pipedrive` — `crm.get_person`, `crm.get_deal`, `crm.add_activity`
- **Acceptance:** Each tool has unit tests with mocked HTTP. Live integration test for Salesforce with a sandbox account.

### B4-02 — Productivity connectors (batch 3)
- **Files:** `api/services/connectors/tools/jira.py`, `github.py`, `asana.py`, `linear.py`
- **Tools:**
  - `jira` — `pm.create_issue`, `pm.get_issue`, `pm.update_issue`, `pm.list_sprint`
  - `github` — `vcs.create_pr`, `vcs.get_pr`, `vcs.list_issues`, `vcs.create_issue`
  - `linear` — `pm.create_issue`, `pm.list_issues`, `pm.update_status`
- **Acceptance:** `jira.create_issue` creates a real Jira issue in a sandbox project.

### B4-03 — Database connectors
- **Files:** `api/services/connectors/tools/postgres_query.py`, `mysql_query.py`, `bigquery.py`
- **Task:** Read-only SQL execution tools. Validate: no write statements (DDL/DML block list). Row limit enforced (max 500). Schema inspection: `db.list_tables`, `db.describe_table`.
- **Acceptance:** Agent runs a `SELECT` query against a tenant's Postgres, results returned as structured data. `UPDATE` statement rejected with clear error.

### B4-04 — Connector SDK
- **File:** `api/sdk/connector_sdk.py` + documentation
- **Task:** Python base class `ConnectorBase` that third-party developers subclass. Must implement: `definition() → ConnectorDefinitionSchema`, `test_connection(credentials) → bool`, and `@tool`-decorated methods. SDK handles credential injection, timeout, error normalisation, and schema generation automatically.
- **Acceptance:** Developer subclasses `ConnectorBase`, decorates two methods with `@tool`, calls `sdk.build_definition()` and gets a valid `ConnectorDefinitionSchema`. Connector uploadable to marketplace via `POST /api/marketplace/connectors`.

### B4-05 — Connector marketplace
- **File:** `api/services/marketplace/connector_registry.py`
- **Task:** Mirror of agent registry for connectors. `publish_connector(publisher_id, definition, package_url)`. Security review required before publish. `GET /api/marketplace/connectors` with same filter/sort model.
- **Acceptance:** Third-party connector appears in marketplace after approval. Tenant installs it and it appears in available connector list.

### B4-06 — Bidirectional webhook management
- **File:** `api/services/connectors/webhooks.py`
- **Task:** `register_webhook(tenant_id, connector_id, event_types)` calls the external API to create a webhook pointing at Maia's receiver. `list_webhooks(tenant_id)`, `deregister_webhook(...)`. Webhooks auto-registered when an agent has an `on_event` trigger matching that connector.
- **Acceptance:** Installing an agent with `trigger: {family: on_event, event_type: "salesforce.deal.stage_changed"}` automatically creates a Salesforce webhook. When deal changes, agent runs.

---

## Phase 5 — Observability and Operations ✅ `done`
**Goal:** Give companies full visibility into their agent fleet — cost, performance, errors, Computer Use session activity, and reliability.

### B5-01 — Run telemetry store
- **File:** `api/services/observability/telemetry.py`
- **Task:** Persist structured telemetry per run: `run_id`, `agent_id`, `tenant_id`, `trigger_type`, `started_at`, `ended_at`, `status`, `token_usage`, `tool_calls: list[{tool_id, latency_ms, success}]`, `gate_events: list[{gate_id, decision, latency_ms}]`, `computer_use_steps: int`, `computer_use_session_id`, `error` if failed. Queryable by agent, date range, status, trigger type.
- **Acceptance:** After 50 runs across 3 agents, telemetry API returns correct aggregates per agent including Computer Use step counts.

### B5-02 — Cost tracking and budget limits
- **File:** `api/services/observability/cost_tracker.py`
- **Task:** Real-time cost per tenant per day. `record_token_cost(tenant_id, agent_id, tokens_in, tokens_out, model)` converts to dollar cost using model pricing table. Computer Use steps billed at `claude-sonnet-4-6` API cost per step. `set_budget_limit(tenant_id, daily_limit_usd)`. When daily limit exceeded, new runs blocked. `budget_exceeded` event emitted.
- **Acceptance:** Tenant with `$1.00` daily limit has runs blocked after that cost is reached. Computer Use steps contribute to daily cost correctly.

### B5-03 — Error classification and alerting
- **File:** `api/services/observability/alerts.py`
- **Task:** Classify run errors: `tool_timeout`, `credential_expired`, `llm_error`, `gate_rejected`, `context_overflow`, `computer_use_step_limit`, `computer_use_session_error`. Alert rules: `set_alert(tenant_id, rule)` — e.g. "if error rate > 20% in 1 hour, notify via Slack". `check_alert_rules(tenant_id)` runs periodically.
- **Acceptance:** Simulating 5 `credential_expired` errors in 30 minutes triggers the alert rule and sends a Slack notification. `computer_use_step_limit` errors classified separately.

---

## Phase 6 — Agent Composition and Advanced Features ✅ `done`
**Goal:** Compound workflows of multiple agents, self-improvement feedback loops, and cross-tenant benchmarking.

### B6-01 — Workflow definition schema
- **File:** `api/schemas/workflow_definition.py`
- **Task:** `WorkflowDefinitionSchema`: `workflow_id`, `name`, `steps: list[WorkflowStep]`, `edges: list[WorkflowEdge]`. A `WorkflowStep` is `{step_id, agent_id, input_mapping: dict, output_key: str}`. A `WorkflowEdge` is `{from_step, to_step, condition}`. Conditions: `output.status == "success"`, `output.confidence > 0.8`. Steps can use Computer Use agents — the browser scene shows all active Computer Use sessions.
- **Acceptance:** A two-step workflow (research agent with Computer Use → draft agent) validates correctly.

### B6-02 — Workflow execution engine
- **File:** `api/services/agents/workflow_executor.py`
- **Task:** Execute a workflow definition. Resolve DAG order via topological sort. Run each step, passing `input_mapping` from prior outputs. Evaluate edge conditions for branching. Emit `workflow_step_started / workflow_step_completed / workflow_branched` activity events. Computer Use sub-sessions are linked to the parent workflow run.
- **Acceptance:** Three-step workflow with a conditional branch executes both happy and fallback paths correctly. Computer Use steps appear in the workflow theatre.

### B6-03 — Agent self-improvement (feedback loop)
- **File:** `api/services/agents/improvement.py`
- **Task:** `record_feedback(tenant_id, agent_id, run_id, original_output, corrected_output, feedback_type)`. `generate_improvement_suggestion(tenant_id, agent_id)` — after 10+ feedback records, calls LLM with current system prompt + feedback examples and returns a suggested system prompt improvement. Human reviews and applies the suggestion.
- **Acceptance:** After 10 corrected runs, improvement suggestion is generated and shown in the agent builder for human review.

### B6-04 — Cross-tenant agent benchmarking (opt-in)
- **File:** `api/services/marketplace/benchmarks.py`
- **Task:** Opt-in tenants contribute anonymous performance signals: task completion rate, average quality score, cost per successful run, Computer Use steps per task. Aggregated per marketplace agent. No prompts, outputs, or company data shared. `opt_in_benchmarking(tenant_id)`, `get_benchmark(marketplace_agent_id)`.
- **Acceptance:** Three opt-in tenants each run an agent 20 times, benchmark shows correct aggregate with no individual tenant data exposed.

---

## Dependency Order

| Phase | Depends On |
|-------|-----------|
| 0 | — (foundation, already done) |
| 1 | Phase 0 |
| 2 | Phase 1 (all connectors + Computer Use) |
| 3 | Phase 2 |
| 4 | Phase 3 |
| 5 | Phase 2 |
| 6 | Phase 3 + Phase 5 |

---

## File Count Summary

| Phase | Slices | Key new directories |
|-------|--------|---------------------|
| 0 | 4 ✅ done | `api/schemas/`, `api/models/`, `api/services/tenants/`, `api/services/agent_definitions/` |
| 1 | 8 + 6 CU = 14 | `api/services/connectors/`, `api/services/computer_use/` |
| 2 | 8 | `api/services/agents/` |
| 3 | 7 | `api/services/marketplace/` |
| 4 | 6 | `api/services/connectors/tools/`, `api/sdk/` |
| 5 | 3 | `api/services/observability/` |
| 6 | 4 | workflow + improvement + benchmarks |
| **Total** | **46** | |
