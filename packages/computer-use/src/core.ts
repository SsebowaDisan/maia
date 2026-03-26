import type { ComputerUseClientConfig } from "./types";

function normalizeApiBase(raw: string | null | undefined): string {
  return String(raw || "").trim().replace(/\/+$/, "");
}

function sanitizeUserId(raw: string | null | undefined): string | null {
  const normalized = String(raw || "").trim();
  return normalized || null;
}

function readPersistedAuthState(): Record<string, unknown> | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem("maia.auth");
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function readUserIdFromPersistedAuth(): string | null {
  const parsed = readPersistedAuthState();
  const state =
    parsed?.state && typeof parsed.state === "object"
      ? (parsed.state as Record<string, unknown>)
      : null;
  const user =
    state?.user && typeof state.user === "object"
      ? (state.user as Record<string, unknown>)
      : null;
  return sanitizeUserId(typeof user?.id === "string" ? user.id : null);
}

function inferApiBase(explicitBase?: string): string {
  const configured = normalizeApiBase(explicitBase);
  if (configured) {
    return configured;
  }
  const envBase = normalizeApiBase(
    (import.meta as { env?: Record<string, string> }).env?.VITE_API_BASE_URL,
  );
  if (envBase) {
    return envBase;
  }
  return "";
}

function inferUserId(explicitUserId?: string | null): string | null {
  const configured = sanitizeUserId(explicitUserId);
  if (configured) {
    return configured;
  }
  const envUserId = sanitizeUserId(
    (import.meta as { env?: Record<string, string> }).env?.VITE_USER_ID,
  );
  if (envUserId) {
    return envUserId;
  }
  return (
    readUserIdFromPersistedAuth() ||
    sanitizeUserId(
      typeof window !== "undefined" ? window.localStorage.getItem("maia.user_id") : null,
    )
  );
}

function buildApiBaseCandidates(apiBase?: string): string[] {
  const bases: string[] = [];
  const configured = inferApiBase(apiBase);
  if (configured) {
    bases.push(configured);
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
    bases.push(configured || "");
  }
  return Array.from(new Set(bases.map(normalizeApiBase)));
}

function buildAuthHeaders(config: ComputerUseClientConfig, initHeaders?: HeadersInit): Headers {
  const headers = new Headers(config.headers || {});
  new Headers(initHeaders || {}).forEach((value, key) => headers.set(key, value));

  const parsed = readPersistedAuthState();
  const state =
    parsed?.state && typeof parsed.state === "object"
      ? (parsed.state as Record<string, unknown>)
      : null;
  const token = typeof state?.accessToken === "string" ? state.accessToken.trim() : "";
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const userId = inferUserId(config.userId);
  if (userId && !headers.has("Authorization") && !headers.has("X-User-Id")) {
    headers.set("X-User-Id", userId);
  }
  return headers;
}

function withUserIdQuery(path: string, userId?: string | null): string {
  const resolvedUserId = inferUserId(userId);
  if (!resolvedUserId || path.includes("user_id=")) {
    return path;
  }
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}user_id=${encodeURIComponent(resolvedUserId)}`;
}

function buildRequestUrl(path: string, base: string, userId?: string | null): string {
  return `${base}${withUserIdQuery(path, userId)}`;
}

function isNetworkError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const name = String((error as { name?: string }).name || "").toLowerCase();
  const message = String(error.message || "").toLowerCase();
  return (
    name === "typeerror" ||
    message.includes("failed to fetch") ||
    message.includes("networkerror")
  );
}

function buildNetworkError(path: string, candidates: string[], cause: unknown): Error {
  const tested = candidates
    .map((base) => (base ? `${base}${path}` : path))
    .join(" | ");
  const causeText = cause instanceof Error ? cause.message : String(cause || "Unknown network failure");
  return new Error(
    `Unable to reach Maia backend. Start or reconnect the Maia API and retry. Endpoint(s): ${tested}. Cause: ${causeText}`,
  );
}

async function fetchApi(
  config: ComputerUseClientConfig,
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const candidates = buildApiBaseCandidates(config.apiBase);
  const fetchImpl = config.fetch || globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    throw new Error("No fetch implementation available for Maia computer-use client.");
  }
  let lastError: unknown = null;

  for (const base of candidates) {
    try {
      return await fetchImpl(buildRequestUrl(path, base, config.userId), {
        ...init,
        headers: buildAuthHeaders(config, init?.headers),
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

function parseErrorMessage(response: Response, text: string): string {
  const trimmed = text.trim();
  if (!trimmed) {
    return `Request failed: ${response.status}`;
  }
  try {
    const parsed = JSON.parse(trimmed) as {
      detail?: { code?: string; message?: string } | string;
      code?: string;
      message?: string;
    };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail.trim();
    }
    if (parsed.detail && typeof parsed.detail === "object") {
      const code = String(parsed.detail.code || "").trim();
      const message = String(parsed.detail.message || "").trim();
      if (message) {
        return code ? `${code}: ${message}` : message;
      }
    }
    const code = String(parsed.code || "").trim();
    const message = String(parsed.message || "").trim();
    if (message) {
      return code ? `${code}: ${message}` : message;
    }
  } catch {
    // fall through
  }
  return trimmed;
}

async function request<T>(
  config: ComputerUseClientConfig,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetchApi(config, path, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(parseErrorMessage(response, text));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  if (!text.trim()) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

export {
  buildRequestUrl,
  fetchApi,
  inferApiBase,
  inferUserId,
  normalizeApiBase,
  request,
  sanitizeUserId,
  withUserIdQuery,
};
