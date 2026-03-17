# Maia — Open Tasks
**Updated:** 2026-03-16
**Scope:** All open work across backend and frontend

---

## Backend Tasks — ALL COMPLETE

| Task | Status | Change |
|---|---|---|
| B-01 `GET /api/agents` description + tags + trigger_family | ✅ Done | `api/routers/agents.py` — enriched list response |
| B-02 `GET /api/marketplace/agents` `is_installed` flag | ✅ Done | `api/routers/marketplace.py` — cross-refs definition_store |
| B-03 `GET /api/agents?trigger_family=` filter | ✅ Done | `api/routers/agents.py` — optional query param |
| B-04 Workflow run history endpoints | ✅ Done (pre-existing) | `api/routers/workflows.py` already had `GET /{id}/runs` and `GET /{id}/runs/{run_id}` |
| B-05 Install response add description + trigger_family | ✅ Done | `api/services/marketplace/installer.py` + `api/routers/marketplace.py` |
| B-06 `GET /api/agents/recent` | ✅ Done | `api/routers/agents.py` — last 5 distinct agents run by user |
| B-07 `ChatRequest.agent_id` field | ✅ Done | `api/schemas.py` — explicit agent selection bypasses intent resolution |
| B-08 Orchestrator explicit agent routing | ✅ Done | `api/services/chat/app_stream_orchestrator.py` — `agent_id` short-circuits `resolve_agent()` |

---

## Frontend Tasks

The backend is fully ready. All APIs needed by the frontend are live.

---

### F-09 — `AgentCommandMenu` component (new)

**What it is:**
A popover panel that opens when the user clicks the **Agent** option in the `ComposerModeSelector`. Lets the user pick which installed agent to talk to. Replaces the current behaviour where clicking "Agent" activates a generic mode with no agent selection.

**What to build:**
New file: `src/app/components/chatMain/composer/AgentCommandMenu.tsx`

**Behaviour:**
- Fetches `GET /api/agents/recent` on mount → shows "Recent" section (last 5 distinct agents run)
- Fetches `GET /api/agents` on mount → shows "All Agents" section
- Search input at top — filters both sections by name and description as user types
- Each row:
  - Agent name (bold, 13px)
  - Description (12px muted, 1 line truncated)
  - Badge: `Scheduled` (blue pill) if `trigger_family === "scheduled"`, else `On demand` (grey pill)
- Keyboard navigation: `↑ ↓` to move, `Enter` to select, `Esc` to close
- When user selects an agent: call `onSelect({ agent_id, name, description, trigger_family })`
- When no agents installed: show link to `/marketplace`
- Loading state: skeleton rows while fetching

**Props:**
```typescript
type AgentCommandMenuProps = {
  open: boolean;
  onClose: () => void;
  onSelect: (agent: { agent_id: string; name: string; description: string; trigger_family: string }) => void;
};
```

**Files:**
- New: `src/app/components/chatMain/composer/AgentCommandMenu.tsx`

---

### F-10 — `ComposerModeSelector` — "Agent" opens `AgentCommandMenu`, shows selected agent name

**Problem:**
Currently clicking "Agent" just sets `composerMode = "company_agent"` with no way to pick a specific agent. The label always says "Agent" regardless of which agent is active.

**Change:**
Add two new props to `ComposerModeSelector`:

```typescript
type ComposerModeSelectorProps = {
  value: ComposerMode;
  onChange: (mode: ComposerMode) => void;
  // NEW:
  activeAgent?: { agent_id: string; name: string } | null;
  onAgentSelect?: (agent: { agent_id: string; name: string; description: string; trigger_family: string } | null) => void;
};
```

**Behaviour changes:**
1. When user clicks "Agent" in the dropdown:
   - Close the mode popover
   - Open `AgentCommandMenu` instead of immediately calling `onChange("company_agent")`
2. When user picks an agent in `AgentCommandMenu`:
   - Call `onChange("company_agent")`
   - Call `onAgentSelect(agent)`
3. The trigger button label:
   - When `value === "company_agent"` AND `activeAgent` is set → show `activeAgent.name` (truncated to 18 chars) instead of "Agent"
   - When `value === "company_agent"` AND no `activeAgent` → show "Agent" (existing behaviour)
4. Clicking the trigger button while already in `company_agent` mode re-opens `AgentCommandMenu` to allow switching agents
5. In the dropdown list, the "Agent" row gets a `▸` arrow icon to indicate it opens a sub-panel

**Files:**
- `src/app/components/ComposerModeSelector.tsx`

---

### F-11 — `useChatMainInteractions` — add `activeAgentId` state + include in send options

**Problem:**
There is no state tracking which agent the user has selected. Even after F-09/F-10 are built, the selected `agent_id` needs to reach the API call.

**Change:**
In `useChatMainInteractions.ts`:

1. Add state:
   ```typescript
   const [activeAgent, setActiveAgent] = useState<{ agent_id: string; name: string } | null>(null);
   ```
2. Add handler:
   ```typescript
   const onAgentSelect = (agent: { agent_id: string; name: string; ... } | null) => {
     setActiveAgent(agent);
     if (agent) onAgentModeChange("company_agent");
   };
   ```
3. Include in `buildSendOptions()` return:
   ```typescript
   return {
     ...existing fields,
     agentId: activeAgent?.agent_id ?? undefined,
   } as const;
   ```
4. Clear `activeAgent` when user switches away from `company_agent` mode:
   ```typescript
   const enableAskMode = () => {
     onAgentModeChange("ask");
     setActiveAgent(null);
   };
   ```
5. Return `activeAgent` and `onAgentSelect` from the hook so `chatMain/app.tsx` can pass them to `ComposerPanel`.

**Files:**
- `src/app/components/chatMain/useChatMainInteractions.ts`

---

### F-12 — `ComposerPanel` — wire `activeAgent` + `onAgentSelect` through to `ComposerModeSelector`

**Problem:**
`ComposerPanel` renders `ComposerModeSelector` but currently has no props for `activeAgent` or `onAgentSelect`.

**Change:**
1. Add to `ComposerPanelProps`:
   ```typescript
   activeAgent?: { agent_id: string; name: string } | null;
   onAgentSelect?: (agent: { agent_id: string; name: string; description: string; trigger_family: string } | null) => void;
   ```
2. Pass them through to `<ComposerModeSelector>`:
   ```tsx
   <ComposerModeSelector
     value={composerMode}
     onChange={...}
     activeAgent={activeAgent}
     onAgentSelect={onAgentSelect}
   />
   ```
3. In `chatMain/app.tsx`, pass `activeAgent` and `onAgentSelect` (from `useChatMainInteractions`) into `<ComposerPanel>`.

**Files:**
- `src/app/components/chatMain/ComposerPanel.tsx`
- `src/app/components/chatMain/app.tsx`

---

### F-13 — `chat.ts` API client — add `agentId` to `sendChatStream` + `sendChat`

**Problem:**
The `sendChatStream` and `sendChat` functions don't send `agent_id` in the request body. The backend `ChatRequest` now accepts it (B-07) but the frontend never sends it.

**Change:**
In `src/api/client/chat.ts`:

1. Add `agentId?: string` to the options type of both `sendChat` and `sendChatStream`
2. Include in the JSON body:
   ```typescript
   body: JSON.stringify({
     ...existing fields,
     agent_id: options?.agentId ?? null,
   })
   ```

**Files:**
- `src/api/client/chat.ts`

---

### F-14 — `sendMessage.ts` — thread `agentId` through `sharedPayload`

**Problem:**
`sendConversationMessage` builds `sharedPayload` and passes it to `sendChatStream`. The `agentId` from `buildSendOptions()` (F-11) needs to be included.

**Change:**
In `sendMessage.ts`, add `agentId` to `sharedPayload`:
```typescript
const sharedPayload = {
  ...existing fields,
  agentId: options?.agentId,
};
```

Also add `agentId?: string` to the `SendOptions` type used in that file.

**Files:**
- `src/app/appShell/conversationChat/sendMessage.ts`

---

## Priority Order

| Priority | Task | Effort | Depends on |
|---|---|---|---|
| 1 | F-09 `AgentCommandMenu` | Medium | B-06 (done) |
| 2 | F-13 `chat.ts` add `agentId` | Tiny | B-07 (done) |
| 3 | F-14 `sendMessage.ts` thread `agentId` | Tiny | F-13 |
| 4 | F-11 `useChatMainInteractions` `activeAgent` state | Small | F-13, F-14 |
| 5 | F-10 `ComposerModeSelector` sub-picker | Small | F-09, F-11 |
| 6 | F-12 `ComposerPanel` wire props | Tiny | F-10, F-11 |
| 7 | F-01 `AgentPickerPanel` (workflow canvas) | Medium | B-02 (done) |
| 8 | F-02 Wire canvas `+` to picker | Small | F-01 |
| 9 | F-03 `StepConfigPanel` cleanup | Small | F-01/F-02 |
| 10 | F-04 Remove dead `listAgents()` | Tiny | F-01–F-03 |
| 11 | F-07 My Agents page | Medium | B-01 (done) |
| 12 | F-06 Post-install "Add to workflow" CTA | Small | F-01 |
| 13 | F-05 `MultiAgentTheatre` live view | Medium | — |
| 14 | F-08 Chat pre-fill from agent detail | Small | — |

**Implement F-09 → F-13 → F-14 → F-11 → F-10 → F-12 in sequence.** That delivers the full Agent Lens flow: click Agent → pick from installed agents → every message routes directly to that agent.
