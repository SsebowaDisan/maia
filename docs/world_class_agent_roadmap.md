# Maia: World-Class Agent Roadmap

## Goal

Make Maia the smartest business agent in the world — one that businesses can use every day for research, decision-making, and action-taking with full transparency.

Two parallel tracks:

- **Research Intelligence**: Five semi-agents (SCOUT, ORACLE, JUDGE, SCRIBE, SENTINEL), multi-source federation, Research Tree decomposition, and LLM-powered claim synthesis with contradiction resolution.
- **Execution Theatre**: Every micro-interaction visible in real time — ghost cursor, scroll animation, evidence crystallization, thought bubbles, Cinema Mode, approval gate spotlight.

The user-facing contract is simple: **"One question. One trusted answer. Watch it happen."**

Three modes map to what people actually want:

| Mode | Sources | Time |
| --- | --- | --- |
| Quick | 8–20 | 6–15 s |
| Deep | 50–120 | 30–90 s |
| Expert | 150–350 | 2–5 min |

---

## Research Inputs

| Source | Key finding |
| --- | --- |
| Existing `events.py` | 200+ event types including `browser_click`, `browser_scroll`, `cursor_x`, `cursor_y`, `scroll_percent`, `highlight_regions`, `snapshot_ref` — theatre data is already captured, just not rendered |
| Existing `research_helpers.py` | `fuse_search_results()` uses reciprocal rank fusion. Adding a `source_weights` param is a one-line signature change with zero impact on existing callers |
| Existing `role_contracts.py` / `agent_roles.py` | Role infrastructure is complete. Semi-agents are specializations of existing roles, not a new orchestration framework |
| Existing `intelligence_sections/claims.py` | Token-based scoring with Jaccard overlap. Function signatures are stable; LLM path can be added as a second-pass without breaking callers |
| Existing `intelligence_sections/contradictions.py` | Lexical contradiction detection caps at 12 units. LLM second-pass added only at `deep_research`+ |
| Existing `live_events.py` | SSE with 200-event backlog, replay, `replay_importance` field already set per event. Narration field is an additive enrichment |
| Existing `ReplayTimeline.tsx` / `BrowserScene.tsx` | Replay timeline and desktop scene are production-grade. Theatre overlays are additive to existing render tree |
| [Apple HIG](https://developer.apple.com/design/human-interface-guidelines/) | Calm motion, strong hierarchy, no debug leakage, no config surfaces exposed to end users |
| ArXiv API | Free, no auth for search. Endpoint: `export.arxiv.org/api/query` |
| SEC EDGAR Full-Text Search | Free, no auth. Endpoint: `efts.sec.gov/LATEST/search-index` |
| NewsAPI | `NEWSAPI_API_KEY` required. Endpoint: `newsapi.org/v2/everything` |
| Reddit JSON API | Free, no auth for read. Endpoint: `reddit.com/search.json` |

---

## Current Code Findings

- [`events.py`](/api/services/agent/events.py) already captures `cursor_x`, `cursor_y`, `scroll_percent`, `highlight_regions`, and `snapshot_ref` on every browser action. Ghost cursor and scroll animation require zero backend changes.
- [`live_events.py`](/api/services/agent/live_events.py) already infers `replay_importance` per event. Adding `narration` is a single enrichment field, cached by `event_type + title` hash.
- [`research_tools.py`](/api/services/agent/tools/research_tools.py) `WebResearchTool.execute_stream()` already runs the query-variants loop that `build_research_tree()` will replace at `deep`+ tiers.
- [`research_helpers.py`](/api/services/agent/tools/research_helpers.py) `fuse_search_results()` is the single RRF fusion point. Adding `source_weights: dict | None = None` keeps all existing callers working with no change.
- [`BingSearchConnector`](/api/services/agent/connectors/bing_search_connector.py) is the exact pattern for all four new connectors (~80 LOC each).
- [`agent_roles.py`](/api/services/agent/orchestration/agent_roles.py) and [`role_contracts.py`](/api/services/agent/orchestration/role_contracts.py) are the only two files that need touching to register new semi-agent tool sets.
- [`guards.py`](/api/services/agent/orchestration/step_execution_sections/guards.py) `run_guard_checks()` is where SENTINEL trust gate plugs in with two lines.
- [`handoff_state.py`](/api/services/agent/orchestration/handoff_state.py) `handoff_pause_notice()` and `maybe_resume_handoff_from_settings()` are already implemented. SENTINEL is a policy layer over these.
- [`BrowserScene.tsx`](/frontend/user_interface/src/app/components/agentDesktopScene/BrowserScene.tsx) already has an interaction overlay slot. Theatre components are composited into existing overlay structure.
- [`VerificationSourceBar.tsx`](/frontend/user_interface/src/app/components/infoPanel/VerificationSourceBar.tsx) renders source cards. Source fly-in is a CSS entry animation on new card arrival.
- [`VerificationTabBar.tsx`](/frontend/user_interface/src/app/components/infoPanel/VerificationTabBar.tsx) is the right place for the trust meter — it already owns the verification footer area.
- `approval_required`, `web_result_opened`, `doc_open` events already exist in `events.py`. Source fly-in and approval gate spotlight need only frontend listeners.

---

## Product Decisions

- Semi-agents (SCOUT, ORACLE, JUDGE, SCRIBE, SENTINEL) are specializations of existing roles in `role_contracts.py`. No new orchestration framework.
- Research Tree decomposition replaces the flat query-variants loop at `deep`+. At `standard` tier, tree supplements rather than replaces.
- All four new search connectors are behind env-var feature flags (`MAIA_ARXIV_ENABLED`, etc). All merge through the existing `fuse_search_results()` unchanged.
- LLM claim extraction and contradiction resolution are second-pass additions. Existing token-based paths remain for `quick` and `standard` tiers.
- Trust gate is three colors only: 🟢 green / 🟡 amber / 🔴 red. No numeric score visible at top level. Scoring details one click away.
- Theatre is on by default. No user settings. No "enable ghost cursor" toggle.
- Cinema Mode is a single button (film icon). It opens full-screen via Fullscreen API, no routing change.
- Thought bubbles appear only for `replay_importance == "critical"` or `"high"` events. Max 40 tokens each. Cached. Never shown for every event.
- The user-visible mode names are Quick, Deep, Expert. Internal tier names (`standard`, `deep_research`, `expert`) never appear in any UI surface.
- Every new data source flows through the existing verification panel — no new UI chrome.

---

## Target Architecture

### Semi-Agent Pipeline

```
AgentOrchestrator
    └─ PlannedStep[]
          ├─ SCOUT   (role: research)   Research Tree + Source Federation
          ├─ ORACLE  (role: analyst)    Claim-level synthesis + ClaimMatrix
          ├─ JUDGE   (role: verifier)   Contradiction resolution + 3-color trust gate
          ├─ SCRIBE  (role: writer)     Evidence-first delivery
          └─ SENTINEL(role: safety)    Action gate + credibility cache
```

### Source Federation

```
WebResearchTool.execute_stream()
    └─ build_research_tree()  →  4–8 structural branches
          └─ per branch: extract_search_variants() + provider plan
                └─ parallel fan-out:
                      Brave Search (existing)
                      Bing Search  (existing)
                      ArXiv        (new, academic signals)
                      SEC EDGAR    (new, financial signals)
                      NewsAPI      (new, news signals)
                      Reddit       (new, sentiment, deep+ only)
                └─ fuse_search_results(source_weights=credibility_map)
                      → ranked, deduplicated, credibility-scored SourceSet
```

### Trust Score Formula

```
trust_score = (corroborated_ratio × 0.45) + (credibility_avg × 0.35) + (source_diversity × 0.20)

gate_color:
  green  →  trust_score ≥ 0.80, no unresolved contradictions
  amber  →  trust_score ≥ 0.55 OR 1 unresolved contradiction
  red    →  trust_score < 0.55 OR 2+ contradictions  →  SCOUT remediation retry
```

### Theatre Data Flow

```
Browser action (click/scroll/hover/type)
    └─ cursor_x, cursor_y, scroll_percent, highlight_regions, snapshot_ref
          └─ SSE stream → frontend event consumer
                └─ GhostCursor   animates cursor to new position
                └─ ScrollReplay  translateY screenshot to new scroll_percent
                └─ ClickRipple   gold ring expands at cursor_x/y
                └─ ThoughtBubble appears if narration field present
                └─ InteractionTrace  rolling 5-position SVG breadcrumb

evidence_crystallized event
    └─ gold glow on highlight_regions
    └─ card launches → lands in evidence strip

trust_score_updated event
    └─ TrustMeter animates width + color

research_branch_started/completed events
    └─ WorkGraph node grows in with opacity + scale animation
```

---

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

---

## Naming Rule

- Scope: these naming rules apply to all modules under `api/` and `frontend/user_interface/src/`.
- Structure must be domain-first, not prefix-first.
- Keep names boring and searchable: lowercase folders, snake_case files for Python, and consistent component naming for React files.
- Prefer grouped paths like:
  - `frontend/user_interface/src/app/components/infoPanel/trust/TrustMeter.tsx`
  - `frontend/user_interface/src/app/components/agentDesktopScene/cursor/GhostCursor.tsx`
  - `frontend/user_interface/src/app/components/agentDesktopScene/overlay/ClickRipple.tsx`
  - `frontend/user_interface/src/app/components/agentActivityPanel/cinema/CinemaMode.tsx`
  - `frontend/user_interface/src/app/components/agentActivityPanel/gate/ApprovalGateCard.tsx`
  - `frontend/user_interface/src/app/components/agentActivityPanel/diff/DiffViewer.tsx`
  - `api/services/agent/research/source_credibility.py`
  - `api/services/agent/intelligence/claim_matrix.py`
- Any move or rename must update imports in the same slice and keep tests green.

---

## Status Legend

- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

---

## Active Slices

---

### S1: Source Federation `todo`

**Goal**: Add four new search connectors and source credibility scoring. Widen the source pool for Deep and Expert tiers without any visible UX change. Every existing call path continues to work unchanged.

**Acceptance criteria**:
- [ ] All four connectors return normalized `{url, title, description, source}` shape
- [ ] `fuse_search_results()` accepts `source_weights` param; existing callers pass nothing and behavior is identical
- [ ] `AgentSource.credibility_score` populated on every result
- [ ] Expert tier (150–350 sources) exists in `research_depth_profile.py`
- [ ] All new connectors are off by default, activated by env vars
- [ ] `pytest -q` passes with no regressions

**Files to create**:

| Path | Purpose |
| --- | --- |
| `api/services/agent/connectors/arxiv_connector.py` | ArXiv search. Endpoint: `export.arxiv.org/api/query`. Free, no key. ~80 LOC following `BingSearchConnector`. |
| `api/services/agent/connectors/sec_edgar_connector.py` | SEC EDGAR search. Endpoint: `efts.sec.gov/LATEST/search-index`. Free, no key. ~80 LOC. |
| `api/services/agent/connectors/newsapi_connector.py` | NewsAPI. Reads `NEWSAPI_API_KEY`. Endpoint: `newsapi.org/v2/everything`. ~80 LOC. |
| `api/services/agent/connectors/reddit_connector.py` | Reddit JSON search. Endpoint: `reddit.com/search.json`. Free, no key. Deep+ only. ~80 LOC. |
| `api/services/agent/research/source_credibility.py` | `score_source_credibility(url) → float`. Domain lookup table. High (0.9+): arxiv.org, sec.gov, .gov, .edu, Reuters, AP. Medium (0.6): established news, Wikipedia. Low (0.3): Reddit, forums. LLM fallback at Expert tier for unknown domains only. |
| `api/tests/test_arxiv_connector.py` | Mock HTTP. Verify output shape. |
| `api/tests/test_sec_edgar_connector.py` | Mock HTTP. Verify output shape. |
| `api/tests/test_newsapi_connector.py` | Mock HTTP. Verify output shape. |
| `api/tests/test_reddit_connector.py` | Mock HTTP. Verify output shape. |
| `api/tests/test_source_credibility.py` | Verify top-50 domains, verify LLM not called for known domains. |

**Files to modify**:

| Path | Change |
| --- | --- |
| `api/services/agent/connectors/registry.py` | Register `arxiv`, `sec_edgar`, `newsapi`, `reddit` behind `MAIA_ARXIV_ENABLED`, `MAIA_SEC_EDGAR_ENABLED`, `MAIA_NEWSAPI_ENABLED`, `MAIA_REDDIT_ENABLED` env vars |
| `api/services/agent/tools/research_helpers.py` | Add `source_weights: dict[str, float] \| None = None` to `fuse_search_results()`. When provided, multiply RRF score by domain credibility weight. Existing callers: no change. |
| `api/services/agent/tools/research_tools.py` | `execute_stream()`: add `_build_provider_plan(depth_tier, intent_signals) → list[(connector_id, weight)]`. Fan out to all configured providers. All results flow into existing `fuse_search_results()`. |
| `api/services/agent/models.py` | Add `credibility_score: float = 0.0` to `AgentSource` dataclass. |
| `api/services/agent/research_depth_profile.py` | Add `"expert"` to `DEPTH_TIERS`. Profile: `max_query_variants=20`, `results_per_query=18`, `fused_top_k=220`, `max_live_inspections=40`, `min_unique_sources=100`, `source_budget_max=350`, `max_research_tree_branches=8`. |
| `api/services/chat/constants.py` | Add feature flag constants: `MAIA_ARXIV_ENABLED`, `MAIA_SEC_EDGAR_ENABLED`, `MAIA_NEWSAPI_ENABLED`, `MAIA_REDDIT_ENABLED`, `MAIA_EXPERT_MODE_ENABLED`. |

---

### S2: Research Tree Decomposition `todo`

**Goal**: Replace the flat query-paraphrase loop with a Research Tree that decomposes the question into 4–8 structurally distinct angles before search begins. The tree becomes visible in the work graph as branches grow in real time.

**Acceptance criteria**:
- [ ] `build_research_tree()` returns 4–8 branches for any non-trivial question
- [ ] Single-word input still produces at least 2 branches
- [ ] At `standard` tier: tree supplements existing variants (no regression)
- [ ] At `deep`+ tiers: tree replaces flat loop
- [ ] Work graph shows hierarchy edges from root query to each branch node
- [ ] Events `research_branch_started` and `research_branch_completed` appear in SSE stream
- [ ] `pytest -q` and `npm test` pass

**Files to create**:

| Path | Purpose |
| --- | --- |
| `api/tests/test_research_tree.py` | Mock LLM, verify branch count, structural distinctness, degenerate input fallback. |

**Files to modify**:

| Path | Change |
| --- | --- |
| `api/services/agent/tools/research_tools.py` | Add `build_research_tree(question, depth_tier, max_branches) → list[ResearchBranch]`. LLM call via `call_json_response()` from `llm_runtime.py`. `temperature=0.0`, `timeout_seconds=12`, `max_tokens=600`. Returns branches with `branch_label`, `sub_question`, `preferred_providers`. Insert call at top of `execute_stream()`. Emit `research_branch_started` when each branch begins, `research_branch_completed` when results are fused. |
| `api/services/agent/events.py` | Add event types `research_branch_started`, `research_branch_completed` to the event taxonomy. |
| `api/services/agent/orchestration/work_graph/builder.py` | On `research_branch_started`: create a `WorkGraphNode` with `node_type="research_branch"`. Add `WorkGraphEdge` with `edge_family="hierarchy"` from root query node to branch node. On `research_branch_completed`: update node status to `completed` with `result_count` and `credibility_avg` in metadata. |

---

### S3: Claim Matrix `todo`

**Goal**: Replace token-based claim scoring with LLM-powered claim extraction. Build a `ClaimMatrix` that maps every factual claim to its supporting and contradicting sources. Wire it into the verification report at `deep`+ tiers.

**Acceptance criteria**:
- [ ] `extract_claims_llm()` extracts structured claims with exact quote attribution
- [ ] `ClaimMatrix` correctly identifies corroborated (2+ independent sources), contested (conflicting sources), and unsupported (1 source only) claims
- [ ] Existing `extract_claim_candidates()` and `score_claim_support()` function signatures unchanged — existing callers not broken
- [ ] LLM path triggered only at `deep_research` or `expert` depth tiers
- [ ] `build_verification_report()` populates `ClaimMatrix` at deep+ tiers
- [ ] `pytest -q` passes

**Files to create**:

| Path | Purpose |
| --- | --- |
| `api/services/agent/intelligence/claim_matrix.py` | `ClaimMatrix` dataclass: `corroborated_claims`, `contested_claims`, `unsupported_claims`, `evidence_map: dict[claim_id, list[source_url]]`, `overall_confidence: float`. `build_claim_matrix(claims, sources) → ClaimMatrix`. |
| `api/tests/test_claim_matrix.py` | Fixture: 3 sources, 2 corroborated claims, 1 contradiction. Verify matrix structure and confidence score. |

**Files to modify**:

| Path | Change |
| --- | --- |
| `api/services/agent/intelligence_sections/claims.py` | Add `extract_claims_llm(text, source_url) → list[StructuredClaim]`. LLM call. Extracts claims with `claim_text`, `exact_quote`, `source_url`. Keeps existing `extract_claim_candidates()` and `score_claim_support()` signatures unchanged. |
| `api/services/agent/intelligence_sections/contradictions.py` | Add `detect_contradictions_llm(claims) → list[ContradictionPair]` as second-pass after existing lexical detection. Add `resolve_contradiction_llm(pair, source_set) → ContradictionResolution` — LLM judges which side has stronger credibility-weighted support. Emit `trust_score_updated` event after each resolution. |
| `api/services/agent/intelligence_sections/verification.py` | In `build_verification_report()`: when `depth_tier in {"deep_research", "expert"}`, call `extract_claims_llm()` and `build_claim_matrix()`. Populate `claim_assessments` and `contradictions` from `ClaimMatrix`. |
| `api/services/agent/events.py` | Add event types `trust_score_updated` (data: `trust_score`, `gate_color`, `reason`) and `evidence_crystallized` (data: `evidence_id`, `source_name`, `extract`, `highlight_regions`, `strength_score`). |
| `api/tests/test_claim_matrix.py` | Already listed above. |
| `api/tests/test_contradiction_resolution.py` | Mock LLM, verify `confirmed` contradiction stays unresolved, `false_positive` is removed, `resolved` contradiction updates claim confidence. |

---

### S4: Trust Gate + Typed Contracts `todo`

**Goal**: Formalize `ResearchOutputContract`, `ClaimMatrixContract`, and `TrustVerdict` as typed dataclasses. Wire `TrustVerdict` into JUDGE's gate logic and expose it to the frontend. Add `trustVerdict`, `claimMatrix`, and `researchTree` to `ChatTurn`.

**Acceptance criteria**:
- [ ] `TrustVerdict.gate_color` is `"green"` / `"amber"` / `"red"` — never any other value
- [ ] Red gate triggers SCOUT remediation retry (uses existing `remediation_attempts` in `ExecutionState`)
- [ ] `trust_score_updated` events appear in SSE stream during JUDGE execution
- [ ] `ChatTurn.trustVerdict`, `ChatTurn.claimMatrix`, `ChatTurn.researchTree` typed in `types.ts`
- [ ] Frontend build (`npm run build`) passes

**Files to create**:

| Path | Purpose |
| --- | --- |
| `api/tests/test_trust_gate.py` | Verify trust_score 0.82 → green, 0.61 → amber, 0.41 → red. Verify red triggers remediation flag. |

**Files to modify**:

| Path | Change |
| --- | --- |
| `api/services/agent/orchestration/models.py` | Add `ResearchOutputContract`, `ClaimMatrixContract`, `TrustVerdict` dataclasses alongside existing `TaskPreparation`, `ExecutionState`. `TrustVerdict`: `gate_color: Literal["green","amber","red"]`, `trust_score: float`, `trust_summary: str`, `resolved_contradictions: list`, `unresolved_contradictions: list`, `release_decision: bool`, `remediation_required: bool`, `remediation_target_claims: list[str]`. |
| `api/services/agent/orchestration/working_context.py` | Extend `scoped_working_context_for_role()` to pass typed contract data between roles. Currently passes `preview: str` only. Add `contract_data: dict \| None = None`. |
| `api/services/agent/orchestration/step_execution_sections/guards.py` | In `run_guard_checks()`: read `TrustVerdict` from working context. If `gate_color == "red"` and `remediation_attempts < max_remediation_attempts`: set `remediation_required = True`, return early before writer steps. If `gate_color == "amber"`: allow writer steps but mark verdict in payload. |
| `frontend/user_interface/src/app/types.ts` | Add to `ChatTurn`: `trustVerdict?: TrustVerdict`, `claimMatrix?: ClaimMatrix`, `researchTree?: ResearchBranch[]`. Add `TrustVerdict`, `ClaimMatrix`, `ResearchBranch`, `ScoredClaim` type definitions. |

---

### S5: Semi-Agent Formalization `todo`

**Goal**: Give SCOUT, ORACLE, JUDGE, SCRIBE, and SENTINEL named identities in the role infrastructure. Expand `role_contracts.py` with their new tool sets. Implement SENTINEL's credibility cache across conversation turns.

**Acceptance criteria**:
- [ ] Work graph labels show SCOUT / ORACLE / JUDGE / SCRIBE / SENTINEL role names
- [ ] Each semi-agent's new tools are in `allowed_tool_ids` in `role_contracts.py`
- [ ] SENTINEL trust gate fires before any `action_class == "execute"` step
- [ ] Amber gate triggers `handoff_pause_notice()` — user must confirm before execution resumes
- [ ] SENTINEL credibility cache persists across turns in the same conversation (namespace: `credibility_cache:`)
- [ ] `pytest -q` passes, no regressions in role routing tests

**Files to modify**:

| Path | Change |
| --- | --- |
| `api/services/agent/orchestration/agent_roles.py` | Add descriptions for SCOUT (research, source federation, credibility scoring), ORACLE (claim synthesis, corroboration matching), JUDGE (contradiction resolution, trust gate), SCRIBE (evidence-first delivery), SENTINEL (action gate, credibility memory). |
| `api/services/agent/orchestration/role_contracts.py` | Expand `allowed_tool_ids` for `research` (SCOUT): add `research.academic.search`, `research.financial.edgar`, `research.news.search`, `research.social.reddit`, `research.source.credibility_score`. Add equivalent entries for `analyst`, `verifier`, `writer`, `safety` roles. |
| `api/services/agent/orchestration/step_execution_sections/guards.py` | Add SENTINEL approval gate: before any tool with `action_class == "execute"` and `risk_level != "low"`, check `TrustVerdict.gate_color`. Amber → `handoff_pause_notice()`. Red → block, do not pause. Green → allow. |

---

### T1: Ghost Cursor + Scroll Replay + Element Glow `todo`

**Goal**: Render MAIA's cursor and scroll position as smooth animations on the browser scene screenshot. All data (`cursor_x`, `cursor_y`, `scroll_percent`) is already in the event stream — this is a pure frontend rendering pass.

**Acceptance criteria**:
- [ ] Ghost cursor moves smoothly between cursor positions via RAF + cubic ease-in-out
- [ ] Cursor has a breathing pulse animation at rest
- [ ] Click events trigger a gold ripple that expands and fades over 600ms at the correct position
- [ ] Hover events render a soft blue halo that stays for the hover duration
- [ ] Scroll events animate `translateY` of the screenshot with a scroll-track indicator on the right edge
- [ ] All animations are ≤ 16ms per frame (no jank)
- [ ] `npm test` passes

**Files to create**:

| Path | Purpose |
| --- | --- |
| `frontend/user_interface/src/app/components/agentDesktopScene/cursor/GhostCursor.tsx` | SVG circle with glow ring. Props: `x: number`, `y: number` (percentages), `isClicking: boolean`, `isHovering: boolean`. RAF tween from previous position to current. Breathing pulse CSS animation at rest. |
| `frontend/user_interface/src/app/components/agentDesktopScene/overlay/ClickRipple.tsx` | CSS keyframe `ripple_expand`: circle starts at 0px, expands to 48px, opacity 0.9 → 0 over 600ms. Gold color for click, blue for hover. Props: `x: number`, `y: number`, `variant: "click" \| "hover"`. |

**Files to modify**:

| Path | Change |
| --- | --- |
| `frontend/user_interface/src/app/components/agentDesktopScene/BrowserScene.tsx` | Import and render `GhostCursor` + `ClickRipple` in existing overlay slot. Track `cursorPos`, `scrollPercent` as state updated from event stream. On `browser_scroll`: apply `transform: translateY(...)` to screenshot image. Add slim scroll-track bar on right edge. |

---

### T2: Timeline Scrub Preview `todo`

**Goal**: Hovering the replay timeline scrubber shows a screenshot thumbnail above the cursor, exactly like a video player timeline. Clicking jumps to that event.

**Acceptance criteria**:
- [ ] Thumbnail appears within 150ms of hover
- [ ] Thumbnail updates as cursor moves across scrubber
- [ ] Thumbnail disappears on mouse leave
- [ ] Clicking any point on the scrubber jumps to the correct event
- [ ] Uses existing `/agent/runs/{run_id}/events/{event_id}/snapshot` endpoint — no new API needed
- [ ] `npm test` passes

**Files to modify**:

| Path | Change |
| --- | --- |
| `frontend/user_interface/src/app/components/agentActivityPanel/ReplayTimeline.tsx` | Add `onMouseMove` handler on scrubber track. Compute event index from cursor position. Fetch `snapshotUrl` for that event (from existing endpoint). Render `<img>` as floating tooltip (position: absolute, bottom: 48px, centered on cursor). Debounce fetch at 80ms. |

---

### T3: Evidence Crystallization + Source Fly-In `todo`

**Goal**: When MAIA finds evidence, the relevant passage on the page glows gold and an evidence card visibly launches from the scene into the evidence strip. When a new source opens, its card flies into the source bar.

**Acceptance criteria**:
- [ ] `evidence_crystallized` event triggers gold glow at `highlight_regions` positions on the scene screenshot
- [ ] A card launches from the glow position with CSS animation: scale up → translate right → scale down → land in evidence strip with bounce
- [ ] Evidence strip card enters with a spring bounce (`cubic-bezier(0.34, 1.56, 0.64, 1)`)
- [ ] `web_result_opened` / `doc_open` events trigger source card fly-in to source bar
- [ ] Source count in source bar increments with a number-flip animation
- [ ] No animation on events that arrived during replay (only during live streaming)
- [ ] `npm test` passes

**Files to create**:

| Path | Purpose |
| --- | --- |
| `frontend/user_interface/src/app/components/agentDesktopScene/overlay/EvidenceCrystal.tsx` | Gold glow region overlay at `highlight_regions` coordinates. On mount: glow + launch animation toward evidence strip. Props: `regions: HighlightRegion[]`, `extract: string`, `onLaunchComplete: () => void`. |
| `frontend/user_interface/src/app/components/infoPanel/source/SourceFlyIn.tsx` | Wrapper that applies entry animation to a new source card. CSS: `translateX(80px) → translateX(0)` + `opacity: 0 → 1` over 350ms ease-out. |

**Files to modify**:

| Path | Change |
| --- | --- |
| `api/services/agent/tools/research_tools.py` | Emit `evidence_crystallized` event when a result exceeds `strength_score` threshold (configurable, default 0.70). Pass `evidence_id`, `source_name`, `extract`, `highlight_regions`, `strength_score` in event data. |
| `api/services/agent/tools/browser_tools.py` | Emit `evidence_crystallized` when PDF evidence is linked (existing `pdf_evidence_linked` event can be extended or the new event emitted in parallel). |
| `frontend/user_interface/src/app/components/agentDesktopScene/BrowserScene.tsx` | Listen for `evidence_crystallized` events. Render `EvidenceCrystal` overlay. |
| `frontend/user_interface/src/app/components/infoPanel/VerificationSourceBar.tsx` | Listen for `web_result_opened` / `doc_open` events in SSE stream. Wrap new card in `SourceFlyIn`. Number-flip animation on source count. |

---

### T4: Live Trust Meter + Research Tree Growing `todo`

**Goal**: A slim animated confidence bar appears in the verification header that pulses live as JUDGE resolves contradictions. Research Tree branches grow into the work graph as SCOUT builds them.

**Acceptance criteria**:
- [ ] Trust meter animates from 0 to current score on first render (spring overshoot)
- [ ] Trust meter transitions smoothly: green → amber → red with no flicker
- [ ] Meter is a slim bar (4px height), not a dial — minimal chrome
- [ ] Research branch nodes appear in the work graph with grow animation (opacity 0 → 1, scale 0.6 → 1.0) on `research_branch_started`
- [ ] On `research_branch_completed`: branch node fills green with result count badge
- [ ] `npm test` passes

**Files to create**:

| Path | Purpose |
| --- | --- |
| `frontend/user_interface/src/app/components/infoPanel/trust/TrustMeter.tsx` | Props: `score: number`, `gate: "green" \| "amber" \| "red"`. Slim bar (4px). Width animates with `transition: width 800ms cubic-bezier(0.34, 1.56, 0.64, 1)`. Color: green (#34C759), amber (#FF9F0A), red (#FF3B30). No text label on the bar itself. |

**Files to modify**:

| Path | Change |
| --- | --- |
| `frontend/user_interface/src/app/components/infoPanel/VerificationTabBar.tsx` | Import and render `TrustMeter` below the tab bar. Subscribe to `trust_score_updated` events from SSE. Update score and gate in state. |
| `frontend/user_interface/src/app/components/workGraph/WorkGraphViewer.tsx` | Handle `research_branch_started` events: add new node via `setNodes`. Node enters with React Flow custom animation (initial opacity 0, `useEffect` → opacity 1 after 50ms frame). Handle `research_branch_completed`: update node data with result count + completed status. |

---

### T5: Thought Bubbles + Keystroke Waterfall `todo`

**Goal**: High-importance events show a floating narration bubble above the browser scene. Typing events render a character cascade animation.

**Acceptance criteria**:
- [ ] Narration appears only for events with `replay_importance == "critical"` or `"high"` AND a `narration` field present
- [ ] Narration bubble slides up from the bottom of the scene, holds 2.5s, fades out
- [ ] Only one thought bubble visible at a time — new one waits for previous to finish
- [ ] Keystroke waterfall fires on `browser_type`, `email_type_body`, `doc_insert_text` events
- [ ] Characters stagger at 15ms intervals, settle, and the cascade fades 500ms after typing ends
- [ ] Both effects are disabled during fast-playback mode (2×)
- [ ] `npm test` passes

**Files to create**:

| Path | Purpose |
| --- | --- |
| `frontend/user_interface/src/app/components/agentDesktopScene/overlay/ThoughtBubble.tsx` | Props: `text: string`, `onDismiss: () => void`. Rounded pill, semi-transparent dark background, white text. CSS: slide up 200ms + fade in, hold 2.5s, fade out 300ms. Max width 320px. |
| `frontend/user_interface/src/app/components/agentDesktopScene/overlay/KeystrokeRain.tsx` | Props: `text: string`. Renders each character staggered at 15ms. Characters appear with `translateY(-8px) → translateY(0)` + `opacity 0 → 1`. Whole cascade fades 500ms after last character. |

**Backend**:

| Path | Change |
| --- | --- |
| `api/services/agent/live_events.py` | Add `build_event_narration(event_type, title, context) → str \| None`. Fires for events with `replay_importance in {"critical", "high"}` only. LLM call: `temperature=0.0`, `max_tokens=40`. Cache key: `sha256(event_type + title[:80])`. Returns `None` if cache hit. Adds `narration: str` field to event `data` before publish. |

**Files to modify**:

| Path | Change |
| --- | --- |
| `frontend/user_interface/src/app/components/agentDesktopScene/BrowserScene.tsx` | Render `ThoughtBubble` when current event has `data.narration`. Queue bubble renders so they do not overlap. Render `KeystrokeRain` when event type is `browser_type`, `email_type_body`, or `doc_insert_text`. Both effects gated by `playbackSpeed < 2`. |

---

### T6: Cinema Mode `todo`

**Goal**: A single "Cinema" button opens a full-screen three-pane view — work graph, live scene, and evidence strip — with timeline scrubber at the bottom and keyboard controls.

**Acceptance criteria**:
- [ ] Cinema Mode opens via Fullscreen API (no routing change)
- [ ] Three panes render correctly at all viewport widths > 1024px
- [ ] Below 1024px: Cinema Mode hides the work graph pane (two panes only)
- [ ] Keyboard controls: Space = play/pause, ← = step back, → = step forward, Esc = exit
- [ ] All theatre features (Ghost Cursor, Evidence Crystallization, Thought Bubbles, etc.) are active in Cinema Mode
- [ ] Exiting Cinema Mode returns to the previous panel state
- [ ] `npm test` passes

**Files to create**:

| Path | Purpose |
| --- | --- |
| `frontend/user_interface/src/app/components/agentActivityPanel/cinema/CinemaMode.tsx` | Full-screen wrapper. CSS Grid: `grid-template-columns: 280px 1fr 300px` (collapses left at <1024px). Left: `WorkGraphViewer` compact. Center: `DesktopViewer` with all theatre overlays. Right: evidence strip + `TrustMeter`. Bottom: `ReplayTimeline` scrubber. Keyboard event listener registered on mount. |

**Files to modify**:

| Path | Change |
| --- | --- |
| `frontend/user_interface/src/app/components/agentActivityPanel/app.tsx` | Add Cinema button (film icon, top-right of panel header). `onClick`: call `document.documentElement.requestFullscreen()`, mount `CinemaMode` as portal overlay. On Esc / fullscreen change event: unmount and restore. |

---

### T7: Interaction Trace + Document Diff + Approval Gate Spotlight `todo`

**Goal**: Show a breadcrumb trail of MAIA's last 5 interactions on the scene. Show before/after diffs for document edits. Dim the entire theatre and show a focused approval card when SENTINEL blocks execution.

**Acceptance criteria**:
- [ ] Interaction trace shows SVG polyline of last 5 cursor positions on the screenshot
- [ ] Oldest dot is 10% opacity, newest is 90% — smooth fade across the trail
- [ ] Trail draws with `stroke-dasharray` animation on each new segment
- [ ] Diff viewer appears for `doc_insert_text` and `email_set_body` events with `content_before` field
- [ ] Diff viewer: inserted text highlighted green, deleted text struck through in red
- [ ] Diff viewer card fades after 3s automatically
- [ ] On `approval_required` event: `backdrop-filter: brightness(0.4)` applied to entire theatre
- [ ] `ApprovalGateCard` renders centered with trust summary, gate color, Approve and Cancel buttons
- [ ] Approve calls existing approval endpoint; theatre undims (400ms fade); execution resumes
- [ ] Cancel calls cancel endpoint; execution stops
- [ ] `npm test` passes

**Files to create**:

| Path | Purpose |
| --- | --- |
| `frontend/user_interface/src/app/components/agentDesktopScene/overlay/InteractionTrace.tsx` | Props: `positions: Array<{x: number, y: number}>`. SVG overlay. `<circle>` for each position, opacity gradient from 0.9 (newest) to 0.1 (oldest). `<polyline>` connecting them, dashed (`stroke-dasharray`). New segment animates in with `stroke-dashoffset` → 0. |
| `frontend/user_interface/src/app/components/agentActivityPanel/diff/DiffViewer.tsx` | Props: `before: string`, `after: string`. Simple inline diff using LCS. Deleted spans: `line-through`, `color: #FF3B30`. Inserted spans: `background: rgba(52,199,89,0.2)`, `color: #34C759`. Renders as floating card in lower-right of scene. Auto-fades after 3000ms. |
| `frontend/user_interface/src/app/components/agentActivityPanel/gate/ApprovalGateCard.tsx` | Props: `trustSummary: string`, `gateColor: "amber" \| "red"`, `onApprove: () => void`, `onCancel: () => void`. Centered modal card. Amber/red border. Pulsing ring animation. Approve button (primary). Cancel button (secondary). |

**Backend**:

| Path | Change |
| --- | --- |
| `api/services/agent/tools/browser_tools.py` | On `doc_open` / `email_draft_create`: capture a 500-char window of current content as `content_before` in event data. Already has access to document state at open time. |

**Files to modify**:

| Path | Change |
| --- | --- |
| `frontend/user_interface/src/app/components/agentDesktopScene/BrowserScene.tsx` | Maintain rolling buffer of last 5 `{cursor_x, cursor_y}` positions for click/hover events. Render `InteractionTrace`. On events with `content_before` + typing: render `DiffViewer`. |
| `frontend/user_interface/src/app/components/agentActivityPanel/app.tsx` | Subscribe to `approval_required` events. On receive: apply `backdrop-filter: brightness(0.4)` to theatre root. Render `ApprovalGateCard` as centered portal. On approve/cancel: remove filter (400ms CSS transition), unmount card. |

---

## Regression Slice (run after each slice)

After every slice, run:

```bash
# Backend
PYTHONPATH=. pytest -q

# Frontend
npm test
npm run build
```

Both must pass before the slice is marked `done`.

---

## Completion Snapshot

*Updated when all slices are validated.*
