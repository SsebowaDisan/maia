import { describe, expect, it } from "vitest";

import { readEventPayload } from "./eventPayload";

describe("readEventPayload", () => {
  it("merges top-level and nested event payload", () => {
    const payload = readEventPayload({
      data: {
        title: "wrapper",
        data: {
          gate_id: "gate_123",
          run_id: "run_456",
        },
      },
      metadata: {
        source: "sse",
      },
    });

    expect(payload.gate_id).toBe("gate_123");
    expect(payload.run_id).toBe("run_456");
    expect(payload.source).toBe("sse");
    expect(payload.title).toBe("wrapper");
  });

  it("prefers explicit top-level values over nested values", () => {
    const payload = readEventPayload({
      data: {
        gate_id: "top_level",
        data: {
          gate_id: "nested",
        },
      },
    });

    expect(payload.gate_id).toBe("top_level");
  });
});
