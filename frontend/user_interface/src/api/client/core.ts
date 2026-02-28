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

const API_BASE = inferApiBase();

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export { API_BASE, request };
