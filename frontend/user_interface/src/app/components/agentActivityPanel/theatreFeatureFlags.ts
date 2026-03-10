function resolveStagedTheatreEnabled(rawValue: unknown): boolean {
  const normalized = String(rawValue ?? "true")
    .trim()
    .toLowerCase();
  return normalized !== "false";
}

export { resolveStagedTheatreEnabled };

