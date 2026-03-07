import { describe, expect, it } from "vitest";

import { edgeColor, edgeWidth } from "./WorkGraphEdge";

describe("WorkGraphEdge helpers", () => {
  it("maps edge families to stable colors", () => {
    expect(edgeColor("evidence")).toBe("#0ea5e9");
    expect(edgeColor("verification")).toBe("#16a34a");
    expect(edgeColor("handoff")).toBe("#7c3aed");
    expect(edgeColor("hierarchy")).toBe("#9ca3af");
  });

  it("assigns width emphasis by family", () => {
    expect(edgeWidth("hierarchy")).toBe(1.4);
    expect(edgeWidth("verification")).toBe(2.1);
    expect(edgeWidth("dependency")).toBe(1.8);
  });
});

