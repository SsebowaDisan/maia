# Maia — Bug Analysis Report
**Date:** 2026-03-14
**Scope:** Full codebase — backend (Python) + frontend (TypeScript/React)

---

## Overall Verdict

| Layer | Status | Critical | High | Medium | Low |
|-------|--------|----------|------|--------|-----|
| Backend | ✅ Clean | 0 | 0 | 3 minor | — |
| Frontend | ⚠️ Bugs found | 1 (fixed) | 4 (1 fixed) | 7 | 1 |

---

## BACKEND

### Result: No critical bugs

All 17 modules analysed. All imports, method signatures, router registrations, and cross-module calls are correct.

Minor notes (non-blocking):
- **Cron parser** in `scheduler.py` is a simplified hand-rolled implementation — falls back to 1-hour delay for unrecognised formats. Not a bug, but a known limitation.
- **Webhook auto-subscribe** in `webhooks.py` has a broad `try/except` — failures are silently swallowed. Acceptable with debug logging but could mask issues in production.
- **Gate `check_gate()`** could be slightly misleading since the new preferred entry point for list-based configs is `check_gates()`. The single-gate version remains correct and is still used internally.

---

## FRONTEND

### FE-BUG-01 — CRITICAL (FIXED) · Missing `api/client/index.ts` barrel file

**File:** `src/api/client/` (entire directory)
**Symptom:** Every import of the form `from "../../api/client"` resolves to a directory with no `index.ts` — TypeScript/bundler fails to resolve the module. **The entire application fails to compile.**

**Scope:** 30+ files across the entire codebase use the bare directory import:
```
src/app/components/chatMain/app.tsx
src/app/appShell/conversationChat/sendMessage.ts
src/app/appShell/eventHelpers.ts
src/app/appShell/fileLibraryJobCreation.ts
src/app/appShell/useConversationChat.ts
src/app/appShell/useFileLibrary.ts
src/app/components/agentActivityPanel/app.tsx
src/app/components/agentActivityPanel/contentDerivation.ts
src/app/components/agentActivityPanel/useAgentActivityDerived.ts
... (20+ more)
```

**Fix:** Created `src/api/client/index.ts` — re-exports all functions and types from `agent.ts`, `chat.ts`, `uploads.ts`, `oauth.ts`, `settings.ts`, and `types.ts`.

---

### FE-BUG-02 — HIGH (FIXED) · `agent.requiredConnectors` null-dereference in `AgentInstallModal`

**File:** `src/app/components/marketplace/AgentInstallModal.tsx:60`

**Problem:** The component correctly declares a safe local variable:
```typescript
const requiredConnectors = agent?.requiredConnectors || [];  // line 20 — safe
```
But then bypasses it and calls `.map()` directly on the raw prop:
```typescript
{agent.requiredConnectors.map(...)}  // line 60 — crashes if undefined
```

`agent` is guaranteed non-null by the early return on line 29, but `requiredConnectors` itself may be absent on a marketplace record. This throws a `TypeError: Cannot read properties of undefined` when an agent without a `requiredConnectors` field is passed.

**Fix:** Changed line 60 to use the safe `requiredConnectors` variable.

**Bonus fix:** The `missingConnectors` filter used `connector.id.includes(required)` (substring match) instead of `connector.id === required` (exact match). A connector named `"google_workspace"` would falsely match a requirement of `"google"`, hiding genuine missing-connector warnings.

---

### FE-BUG-03 — HIGH · Unsafe `as` cast on SSE events without validation

**File:** `src/app/appShell/conversationChat/sendMessage.ts:396`
```typescript
const payload = event.event as AgentActivityEvent;
```

**Problem:** `event.event` is typed as `unknown` from the SSE stream. Casting directly to `AgentActivityEvent` without a type guard means any malformed event from the backend passes through silently, and downstream code reading `payload.run_id`, `payload.event_type`, etc. may access `undefined` properties.

**Recommended fix:** Add a minimal guard before using `payload`:
```typescript
const payload = event.event as AgentActivityEvent;
if (!payload || typeof payload.event_type !== "string") return;
```

**Status:** Not fixed yet — needs review of the event pipeline design first.

---

### FE-BUG-04 — MEDIUM · Step-reset missing when `AgentInstallModal` re-opens

**File:** `src/app/components/marketplace/AgentInstallModal.tsx`

**Problem:** `step` state is initialised to `1` but never reset when the modal closes and re-opens with a different agent. If a user opens agent A (reaches step 3), closes, then opens agent B, they see step 3 of agent B.

**Recommended fix:** Add a `useEffect` that resets `step`, `connectorMap`, and `gateEnabled` when `agent` changes:
```typescript
useEffect(() => {
  if (open) {
    setStep(1);
    setConnectorMap({});
    setGateEnabled({});
  }
}, [open, agent?.id]);
```

**Status:** Not fixed — low risk until real API install flow is wired.

---

### FE-BUG-05 — MEDIUM · `approveAgentRunGate` / `rejectAgentRunGate` POST missing `Content-Type` header

**File:** `src/api/client/agent.ts:244–259`
```typescript
function approveAgentRunGate(runId: string, gateId: string) {
  return request<...>(`/api/agents/runs/.../approve`, {
    method: "POST",
    // ← No Content-Type header
  });
}
```

**Problem:** Both gate action endpoints POST with no body and no `Content-Type` header. The FastAPI backend accepts this fine (no body required), but some proxies and CDNs reject headerless POSTs. For consistency with all other mutation calls and future-proofing, a `Content-Type: application/json` header should be added.

**Status:** Not fixed — low risk in current deployment.

---

### FE-BUG-06 — MEDIUM · BrowserScene disconnected from real Computer Use SSE stream

**File:** `src/app/components/agentDesktopScene/BrowserScene.tsx`

**Problem:** `BrowserScene` renders a screenshot viewer and accepts `screenshotB64` as a prop, but nothing in the application actually connects this prop to the live Computer Use SSE stream at `GET /api/computer-use/sessions/{id}/stream`. The component is a display shell with no subscription logic.

**Impact:** Clicking "run with Computer Use" starts a session on the backend but the browser window in the UI stays blank. This is the highest-priority UX gap (documented in `frontend_tasks.md` as F-04).

**Status:** Not a code bug but a missing wire. Tracked in F-04.

---

### FE-BUG-07 — MEDIUM · `sendMessage.ts` setClarificationPrompt type is too loose

**File:** `src/app/appShell/conversationChat/sendMessage.ts:412`
```typescript
setClarificationPrompt((previous: { runId?: string } | null) => {
```

**Problem:** The setter callback annotates `previous` as `{ runId?: string } | null` — an inline structural type — rather than the `ClarificationPrompt | null` type imported from `app/types.ts`. TypeScript won't catch if `previous` is used with fields that exist on `ClarificationPrompt` but not this inline type.

**Recommended fix:**
```typescript
setClarificationPrompt((previous: ClarificationPrompt | null) => {
```

**Status:** Not fixed — cosmetic type safety issue, no runtime impact.

---

---

### FE-BUG-08 — HIGH · `normalizeAgentActivityEvent` under-validates before casting

**File:** `src/app/appShell/eventHelpers.ts:99–124`
```typescript
const candidate = payload as Record<string, unknown>;
if (!("event_id" in candidate) || !("event_type" in candidate)) {
  return null;
}
const normalized = {
  ...(candidate as AgentActivityEvent),  // ← spreads unknown fields
  metadata: ...
} as AgentActivityEvent;
```

**Problem:** Only `event_id` and `event_type` are checked. `AgentActivityEvent` also requires `title`, `detail`, `timestamp`, `event_family`, and more. If the backend omits any of these, the function returns a structurally incomplete object typed as `AgentActivityEvent`. Downstream consumers of `payload.title` or `payload.detail` silently receive `undefined`.

**Status:** Not fixed.

---

### FE-BUG-09 — HIGH · `scrollLatestTurnToTop` missing from `useEffect` dependency array

**File:** `src/app/components/chatMain/app.tsx:340–348`
```typescript
useEffect(() => {
  if (!isSending) return;
  const rafId = window.requestAnimationFrame(() => {
    scrollLatestTurnToTop();  // ← stale closure — not in deps
  });
  return () => window.cancelAnimationFrame(rafId);
}, [chatTurns.length, isSending, isActivityStreaming]);
```

**Problem:** `scrollLatestTurnToTop` (defined at line 278) closes over `chatTurns` and `contentScrollRef`. It is not memoised and not listed as a dependency. If `chatTurns` content changes without changing its length (e.g., last turn content updates), the effect does not re-run, and the stale closure scrolls based on outdated turn data. React's exhaustive-deps rule flags this.

**Status:** Not fixed.

---

### FE-BUG-10 — MEDIUM · Wrong index used when mapping upload results back to attachments

**File:** `src/app/components/chatMain/interactions/fileUpload.ts:60–76`
```typescript
const pendingIdx = pending.findIndex((item) => item.id === attachment.id);
// pendingIdx = position in the `pending` attachment array
const item = result.items[pendingIdx];  // ← indexing result.items with wrong index
```

**Problem:** `pendingIdx` is the index of the attachment within the local `pending` array (which may contain many unrelated attachments). `result.items` is indexed by position in the upload batch sent to the server — a different array. If previous attachments in `pending` were already indexed (skipped by the `pendingIdx === -1` check in the outer `.map`), the indices diverge and `item` is the wrong upload result or `undefined`, silently assigning the wrong `fileId` to an attachment or marking a successful upload as failed.

**Status:** Not fixed.

---

### FE-BUG-11 — MEDIUM · Widget props spread untyped into typed component

**File:** `src/app/components/messages/BlockRenderer.tsx:119–124`
```typescript
const Widget = widgetRegistry[block.widget.kind as keyof typeof widgetRegistry];
if (!Widget) return null;
return <Widget {...block.widget.props} />;  // props: Record<string, unknown>
```

**Problem:** `block.widget.props` is typed as `Record<string, unknown>`. Spreading it into `Widget` (which expects `LensWidgetProps` or similar) bypasses TypeScript's prop validation entirely. If the backend sends wrong or missing props for a widget kind, the widget renders with broken data and TypeScript produces no compile-time error at the call site.

**Status:** Not fixed.

---

### FE-BUG-12 — LOW · BrowserScene scroll observer captures stale `frameDocument` reference

**File:** `src/app/components/agentDesktopScene/BrowserScene.tsx:209–252`

**Problem:** `bindFrameScrollObserver` captures `frameDocument` and `frameWindow` at the time the iframe first loads. If the iframe navigates internally after that (e.g., redirects, hash changes), `frameDocument` in the closure points to the original document. Scroll position calculations will then read from the old document, producing incorrect `frameScrollPercent` values. The cleanup effect at line 193 only fires when the `frameUrl` **prop** changes, not on in-frame navigations.

**Status:** Not fixed — low risk while BrowserScene is still a static screenshot viewer.

---

## Summary: Fixes Applied

| ID | Severity | File | Fix |
|----|----------|------|-----|
| FE-BUG-01 | CRITICAL | `src/api/client/index.ts` | **Created** barrel file |
| FE-BUG-02 | HIGH | `AgentInstallModal.tsx:60` | **Fixed** null-dereference + loose match |

## Summary: Fixes Pending

| ID | Severity | File | Action needed |
|----|----------|------|--------------|
| FE-BUG-03 | HIGH | `sendMessage.ts:396` | Add type guard before casting SSE event |
| FE-BUG-04 | MEDIUM | `AgentInstallModal.tsx` | Reset state on modal re-open |
| FE-BUG-05 | MEDIUM | `agent.ts:244–259` | Add `Content-Type` header to gate POSTs |
| FE-BUG-06 | MEDIUM | `BrowserScene.tsx` | Wire to Computer Use SSE stream (see F-04) |
| FE-BUG-07 | MEDIUM | `sendMessage.ts:412` | Tighten `setClarificationPrompt` type |
| FE-BUG-08 | HIGH | `eventHelpers.ts:99–124` | Validate all required fields before casting to `AgentActivityEvent` |
| FE-BUG-09 | HIGH | `chatMain/app.tsx:340` | Add `scrollLatestTurnToTop` to `useEffect` deps or memoize it |
| FE-BUG-10 | MEDIUM | `fileUpload.ts:60–76` | Fix index mismatch between `pending` array and `result.items` |
| FE-BUG-11 | MEDIUM | `BlockRenderer.tsx:124` | Validate widget props against expected type before spread |
| FE-BUG-12 | LOW | `BrowserScene.tsx:209` | Re-bind scroll observer on iframe internal navigation |
