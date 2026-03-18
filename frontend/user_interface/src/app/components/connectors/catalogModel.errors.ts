import { uniqueIds } from "./catalogModel.types";

function sameIdList(left: string[], right: string[]): boolean {
  const a = [...uniqueIds(left)].sort();
  const b = [...uniqueIds(right)].sort();
  if (a.length !== b.length) {
    return false;
  }
  return a.every((value, index) => value === b[index]);
}

export function findChangedConnectorId(
  previous: Record<string, string[]>,
  next: Record<string, string[]>,
): string | null {
  const keys = uniqueIds([...Object.keys(previous), ...Object.keys(next)]);
  for (const key of keys) {
    if (!sameIdList(previous[key] || [], next[key] || [])) {
      return key;
    }
  }
  return null;
}

export function isBindingMissingError(error: unknown): boolean {
  const text = String(error || "").toLowerCase();
  return (
    text.includes("no binding found") ||
    text.includes("not found") ||
    text.includes("request failed: 404")
  );
}

export function isNotFoundError(error: unknown): boolean {
  const text = String(error || "").toLowerCase();
  return text.includes("404") || text.includes("not found");
}
