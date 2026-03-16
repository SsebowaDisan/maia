function normalizeApiBase(raw: string | null | undefined): string {
  return String(raw || "").trim().replace(/\/+$/, "");
}

function inferApiBase() {
  const envBase = normalizeApiBase(
    (import.meta as { env?: Record<string, string> }).env?.VITE_API_BASE_URL,
  );
  if (envBase) {
    return envBase;
  }

  if (typeof window === "undefined") {
    return "";
  }

  const { port } = window.location;
  // In local Vite dev, prefer same-origin `/api` so proxy handles routing/CORS.
  if (port === "5173" || port === "4173") {
    return "";
  }

  return "";
}

function sanitizeUserId(raw: string | null | undefined): string | null {
  if (!raw) {
    return null;
  }
  const normalized = raw.trim();
  return normalized || null;
}

function readUserIdFromPersistedAuth(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem("maia.auth");
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as { state?: { user?: { id?: string } } };
    return sanitizeUserId(parsed?.state?.user?.id || null);
  } catch {
    return null;
  }
}

function inferUserId() {
  const envUserId = sanitizeUserId((import.meta as { env?: Record<string, string> }).env?.VITE_USER_ID);
  if (envUserId) {
    return envUserId;
  }
  if (typeof window === "undefined") {
    return null;
  }

  // Prefer authenticated identity when available so chat data does not appear
  // to "disappear" due to URL/query-scoped dev user switches.
  const fromAuth = readUserIdFromPersistedAuth();
  if (fromAuth) {
    window.localStorage.setItem("maia.user_id", fromAuth);
    return fromAuth;
  }

  const fromStorage = sanitizeUserId(window.localStorage.getItem("maia.user_id"));
  if (fromStorage) {
    // Only allow query override when explicitly forced. This prevents
    // accidental user scope switches from shared URLs and QA links.
    const query = new URLSearchParams(window.location.search);
    const fromQuery = sanitizeUserId(query.get("user_id"));
    const forceSwitch = String(query.get("force_user_id") || "").trim() === "1";
    if (fromQuery && forceSwitch) {
      window.localStorage.setItem("maia.user_id", fromQuery);
      return fromQuery;
    }
    return fromStorage;
  }

  const fromQuery = sanitizeUserId(new URLSearchParams(window.location.search).get("user_id"));
  if (fromQuery) {
    window.localStorage.setItem("maia.user_id", fromQuery);
    return fromQuery;
  }

  // Keep user-scoped conversation state stable across reloads even when no
  // explicit user id is supplied in URL/env.
  const fallbackUserId = "default";
  window.localStorage.setItem("maia.user_id", fallbackUserId);
  return fallbackUserId;
}

function withUserIdHeaders(initHeaders?: HeadersInit) {
  const headers = new Headers(initHeaders || {});

  // Prefer JWT Bearer token when available (production auth)
  try {
    const raw = window.localStorage.getItem("maia.auth");
    if (raw) {
      const parsed = JSON.parse(raw) as { state?: { accessToken?: string } };
      const token = parsed?.state?.accessToken;
      if (token && !headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${token}`);
      }
    }
  } catch {
    // ignore — fall through to legacy header
  }

  // Legacy fallback: X-User-Id header (dev mode / MAIA_AUTH_DISABLED=true)
  if (ACTIVE_USER_ID && !headers.has("X-User-Id") && !headers.has("Authorization")) {
    headers.set("X-User-Id", ACTIVE_USER_ID);
  }
  return headers;
}

function withUserIdQuery(path: string) {
  if (!ACTIVE_USER_ID || path.includes("user_id=")) {
    return path;
  }
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}user_id=${encodeURIComponent(ACTIVE_USER_ID)}`;
}

const API_BASE = inferApiBase();
const ACTIVE_USER_ID = inferUserId();

function isNetworkError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const name = String((error as { name?: string }).name || "").toLowerCase();
  const message = String(error.message || "").toLowerCase();
  if (name === "aborterror") {
    return false;
  }
  return (
    name === "typeerror" ||
    message.includes("failed to fetch") ||
    message.includes("networkerror")
  );
}

function buildApiBaseCandidates(): string[] {
  const bases: string[] = [];
  if (API_BASE) {
    bases.push(API_BASE);
  }
  if (typeof window !== "undefined") {
    const { hostname, port } = window.location;
    if (port === "5173" || port === "4173") {
      bases.push("");
      bases.push(`http://${hostname || "127.0.0.1"}:8000`);
      bases.push("http://127.0.0.1:8000");
      bases.push("http://localhost:8000");
    } else {
      bases.push("");
    }
  } else {
    bases.push(API_BASE || "");
  }
  return Array.from(
    new Set(
      bases
        .map((value) => normalizeApiBase(value))
        .filter((value, index, rows) => rows.indexOf(value) === index),
    ),
  );
}

function buildRequestUrl(path: string, base: string): string {
  const suffix = withUserIdQuery(path);
  return `${base}${suffix}`;
}

function buildNetworkError(path: string, candidates: string[], cause: unknown): Error {
  const tested = candidates
    .map((base) => (base ? `${base}${path}` : path))
    .join(" | ");
  const causeText = cause instanceof Error ? cause.message : String(cause || "Unknown network failure");
  return new Error(
    `Unable to reach Maia backend. Start/restart API server and retry. Endpoint(s): ${tested}. Cause: ${causeText}`,
  );
}

async function fetchApi(path: string, init?: RequestInit): Promise<Response> {
  const candidates = buildApiBaseCandidates();
  let lastError: unknown = null;

  for (const base of candidates) {
    try {
      return await fetch(buildRequestUrl(path, base), {
        ...init,
        headers: withUserIdHeaders(init?.headers),
      });
    } catch (error) {
      lastError = error;
      if (!isNetworkError(error)) {
        throw error;
      }
    }
  }

  throw buildNetworkError(path, candidates, lastError);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchApi(path, init);

  if (!response.ok) {
    const text = await response.text();
    const trimmed = text.trim();
    if (trimmed) {
      let parsedMessage = "";
      try {
        const parsed = JSON.parse(trimmed) as {
          detail?: {
            code?: string;
            message?: string;
            details?: Record<string, unknown>;
          } | string;
          code?: string;
          message?: string;
        };
        if (typeof parsed?.detail === "string" && parsed.detail.trim()) {
          parsedMessage = parsed.detail.trim();
        }
        if (!parsedMessage && parsed?.detail && typeof parsed.detail === "object") {
          const code = String(parsed.detail.code || "").trim();
          const message = String(parsed.detail.message || "").trim();
          if (message) {
            parsedMessage = code ? `${code}: ${message}` : message;
          }
        }
        if (!parsedMessage) {
          const code = String(parsed?.code || "").trim();
          const message = String(parsed?.message || "").trim();
          if (message) {
            parsedMessage = code ? `${code}: ${message}` : message;
          }
        }
      } catch {
        parsedMessage = "";
      }
      if (parsedMessage) {
        throw new Error(parsedMessage);
      }
      throw new Error(trimmed);
    }
    throw new Error(`Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export { ACTIVE_USER_ID, API_BASE, fetchApi, request, withUserIdHeaders, withUserIdQuery };
