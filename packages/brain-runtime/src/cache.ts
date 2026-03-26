/**
 * LLM response caching — avoid duplicate calls, save money and latency.
 *
 * Two strategies:
 * - In-memory: fast, lost on restart (default)
 * - Custom: pass your own get/set for Redis, SQLite, etc.
 *
 * Cache key = SHA-256(model + system + user prompt).
 * TTL-based expiry. Max entries with LRU eviction.
 */

export interface CacheEntry {
  text: string;
  tokensUsed: number;
  costUsd: number;
  model: string;
  cachedAt: number;
}

export interface CacheOptions {
  /** Enable caching (default: true). */
  enabled?: boolean;
  /** Time-to-live in ms (default: 30 minutes). */
  ttlMs?: number;
  /** Max entries before LRU eviction (default: 500). */
  maxEntries?: number;
  /** Custom get function (for Redis, SQLite, etc). */
  get?: (key: string) => Promise<CacheEntry | null>;
  /** Custom set function. */
  set?: (key: string, entry: CacheEntry) => Promise<void>;
}

export interface LLMCache {
  get(key: string): Promise<CacheEntry | null>;
  set(key: string, entry: CacheEntry): Promise<void>;
  has(key: string): Promise<boolean>;
  clear(): void;
  stats(): CacheStats;
}

export interface CacheStats {
  hits: number;
  misses: number;
  entries: number;
  hitRate: number;
  savedUsd: number;
}

/**
 * Create an LLM cache instance.
 */
export function createCache(options: CacheOptions = {}): LLMCache {
  const ttl = options.ttlMs ?? 30 * 60 * 1000;
  const maxEntries = options.maxEntries ?? 500;
  const customGet = options.get;
  const customSet = options.set;

  // In-memory store with LRU ordering
  const store = new Map<string, CacheEntry>();
  const accessOrder: string[] = [];
  let hits = 0;
  let misses = 0;
  let savedUsd = 0;

  async function get(key: string): Promise<CacheEntry | null> {
    if (customGet) {
      const entry = await customGet(key);
      if (entry && !isExpired(entry, ttl)) {
        hits++;
        savedUsd += entry.costUsd;
        return entry;
      }
      misses++;
      return null;
    }

    const entry = store.get(key);
    if (!entry) { misses++; return null; }
    if (isExpired(entry, ttl)) { store.delete(key); misses++; return null; }

    // Move to end of access order (LRU)
    const idx = accessOrder.indexOf(key);
    if (idx >= 0) accessOrder.splice(idx, 1);
    accessOrder.push(key);

    hits++;
    savedUsd += entry.costUsd;
    return entry;
  }

  async function set(key: string, entry: CacheEntry): Promise<void> {
    if (customSet) { await customSet(key, entry); return; }

    // Evict oldest if over limit
    while (store.size >= maxEntries && accessOrder.length > 0) {
      const oldest = accessOrder.shift()!;
      store.delete(oldest);
    }

    store.set(key, entry);
    accessOrder.push(key);
  }

  async function has(key: string): Promise<boolean> {
    const entry = await get(key);
    return entry !== null;
  }

  function clear(): void {
    store.clear();
    accessOrder.length = 0;
  }

  function stats(): CacheStats {
    const total = hits + misses;
    return {
      hits, misses,
      entries: store.size,
      hitRate: total > 0 ? Math.round((hits / total) * 10000) / 10000 : 0,
      savedUsd: Math.round(savedUsd * 10000) / 10000,
    };
  }

  return { get, set, has, clear, stats };
}

/**
 * Generate a cache key from prompt content.
 * Uses a fast hash since we don't need cryptographic strength.
 */
export function cacheKey(model: string, systemPrompt: string, userPrompt: string): string {
  const input = `${model}::${systemPrompt}::${userPrompt}`;
  // FNV-1a 64-bit hash as hex — fast, good distribution
  let h1 = 0x811c9dc5;
  let h2 = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    const c = input.charCodeAt(i);
    h1 = Math.imul(h1 ^ (c & 0xff), 0x01000193);
    h2 = Math.imul(h2 ^ ((c >> 8) & 0xff), 0x01000193);
  }
  return `llm_${(h1 >>> 0).toString(16)}${(h2 >>> 0).toString(16)}`;
}

function isExpired(entry: CacheEntry, ttlMs: number): boolean {
  return Date.now() - entry.cachedAt > ttlMs;
}