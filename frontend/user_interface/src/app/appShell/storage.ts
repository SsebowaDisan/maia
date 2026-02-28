export function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function readStoredWidth(key: string, fallback: number) {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = Number(window.localStorage.getItem(key) || "");
  return Number.isFinite(value) ? value : fallback;
}

export function readStoredText(key: string, fallback: string) {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = window.localStorage.getItem(key);
  return value || fallback;
}

export function readStoredJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = window.localStorage.getItem(key);
  if (!value) {
    return fallback;
  }
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}
