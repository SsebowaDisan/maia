type TheatreMetricPayload = Record<string, unknown>;

function emitTheatreMetric(name: string, payload: TheatreMetricPayload = {}) {
  if (typeof window === "undefined") {
    return;
  }
  const detail = {
    name: String(name || "").trim(),
    payload,
    timestamp: new Date().toISOString(),
  };
  window.dispatchEvent(new CustomEvent("maia:theatre_metric", { detail }));
}

export { emitTheatreMetric };

