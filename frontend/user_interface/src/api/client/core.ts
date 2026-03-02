function inferApiBase() {
  const envBase = (import.meta as { env?: Record<string, string> }).env?.VITE_API_BASE_URL;
  if (envBase) {
    return envBase;
  }

  if (typeof window === "undefined") {
    return "";
  }

  const { hostname, port } = window.location;
  if (port === "5173" || port === "4173") {
    return `http://${hostname || "127.0.0.1"}:8000`;
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

function inferUserId() {
  const envUserId = sanitizeUserId((import.meta as { env?: Record<string, string> }).env?.VITE_USER_ID);
  if (envUserId) {
    return envUserId;
  }
  if (typeof window === "undefined") {
    return null;
  }
  const fromQuery = sanitizeUserId(new URLSearchParams(window.location.search).get("user_id"));
  if (fromQuery) {
    window.localStorage.setItem("maia.user_id", fromQuery);
    return fromQuery;
  }
  return sanitizeUserId(window.localStorage.getItem("maia.user_id"));
}

function withUserIdHeaders(initHeaders?: HeadersInit) {
  const headers = new Headers(initHeaders || {});
  if (ACTIVE_USER_ID && !headers.has("X-User-Id")) {
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${withUserIdQuery(path)}`, {
    ...init,
    headers: withUserIdHeaders(init?.headers),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export { ACTIVE_USER_ID, API_BASE, request, withUserIdHeaders, withUserIdQuery };
