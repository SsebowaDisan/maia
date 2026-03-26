/**
 * Agent memory — persists decisions, lessons, and preferences across runs.
 * Agents can reference past conversations: "Last time we split ACV by segment."
 */

export interface MemoryEntry {
  /** What was decided or learned. */
  content: string;
  /** Which run this came from. */
  runId: string;
  /** When it was recorded. */
  timestamp: string;
  /** Which agent recorded it. */
  agentId: string;
  /** Type of memory. */
  type: "decision" | "lesson" | "preference" | "fact";
  /** Relevance tags for retrieval. */
  tags: string[];
}

export interface MemoryStore {
  entries: MemoryEntry[];
  maxEntries: number;
}

/**
 * Create a new memory store.
 */
export function createMemoryStore(maxEntries: number = 100): MemoryStore {
  return { entries: [], maxEntries };
}

/**
 * Record a new memory. Auto-evicts oldest if over limit.
 */
export function recordMemory(
  store: MemoryStore,
  entry: Omit<MemoryEntry, "timestamp">,
): void {
  store.entries.push({ ...entry, timestamp: new Date().toISOString() });
  if (store.entries.length > store.maxEntries) {
    store.entries = store.entries.slice(-store.maxEntries);
  }
}

/**
 * Recall memories relevant to a query.
 * Scores by tag overlap and recency.
 */
export function recallMemories(
  store: MemoryStore,
  query: string,
  limit: number = 5,
): MemoryEntry[] {
  if (!store.entries.length) return [];

  const queryTokens = new Set(
    query.toLowerCase().split(/\s+/).filter((t) => t.length >= 3),
  );
  if (!queryTokens.size) return store.entries.slice(-limit);

  const scored = store.entries.map((entry) => {
    const entryTokens = new Set([
      ...entry.content.toLowerCase().split(/\s+/),
      ...entry.tags.map((t) => t.toLowerCase()),
    ]);
    let overlap = 0;
    for (const token of queryTokens) {
      if (entryTokens.has(token)) overlap++;
    }
    const relevance = queryTokens.size > 0 ? overlap / queryTokens.size : 0;
    const recency = Date.now() - new Date(entry.timestamp).getTime();
    const recencyScore = Math.max(0, 1 - recency / (30 * 24 * 60 * 60 * 1000)); // 30-day decay
    return { entry, score: relevance * 0.7 + recencyScore * 0.3 };
  });

  return scored
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .filter((s) => s.score > 0.05)
    .map((s) => s.entry);
}

/**
 * Build a memory context string for injection into agent prompts.
 */
export function memoryContextPrompt(
  store: MemoryStore,
  query: string,
): string {
  const memories = recallMemories(store, query, 5);
  if (!memories.length) return "";

  const lines = memories.map((m) =>
    `- [${m.type}] ${m.content} (from run ${m.runId.slice(0, 8)})`,
  );
  return (
    "\nRelevant context from previous runs:\n"
    + lines.join("\n")
    + "\n\nReference these naturally if relevant — e.g., 'Like last time...' or 'We decided earlier...'"
  );
}

/**
 * Auto-extract decisions from a conversation thread.
 * Looks for agreement, summary, and decision intents.
 */
export function extractDecisions(
  runId: string,
  turns: Array<{ agentId: string; intent: string; content: string }>,
): MemoryEntry[] {
  const decisions: MemoryEntry[] = [];
  for (const turn of turns) {
    if (turn.intent === "summarize" || turn.intent === "agree") {
      if (turn.content.length >= 20 && turn.content.length <= 200) {
        decisions.push({
          content: turn.content,
          runId,
          timestamp: new Date().toISOString(),
          agentId: turn.agentId,
          type: "decision",
          tags: turn.content
            .toLowerCase()
            .split(/\s+/)
            .filter((t) => t.length >= 4)
            .slice(0, 5),
        });
      }
    }
  }
  return decisions;
}

/**
 * Serialize store to JSON for persistence.
 */
export function serializeMemoryStore(store: MemoryStore): string {
  return JSON.stringify(store);
}

/**
 * Deserialize store from JSON.
 */
export function deserializeMemoryStore(json: string): MemoryStore {
  try {
    const parsed = JSON.parse(json);
    return {
      entries: Array.isArray(parsed.entries) ? parsed.entries : [],
      maxEntries: parsed.maxEntries ?? 100,
    };
  } catch {
    return createMemoryStore();
  }
}