import { describe, expect, it } from "vitest";

import type { WorkGraphNode } from "./work_graph_types";
import { extractNodeRiskReason, shouldShowVerifierAction } from "./evidenceSync";

describe("evidence sync helpers", () => {
  it("extracts risk reason from verifier metadata", () => {
    const node: WorkGraphNode = {
      id: "node.verify",
      title: "Verify numbers",
      status: "blocked",
      metadata: {
        verifier_conflict_reason: "Sources disagree on Q4 totals.",
      },
    };
    expect(extractNodeRiskReason(node)).toBe("Sources disagree on Q4 totals.");
  });

  it("shows verifier action for blocked or low-confidence nodes", () => {
    const blockedNode: WorkGraphNode = {
      id: "node.blocked",
      title: "Blocked",
      status: "blocked",
    };
    const lowConfidenceNode: WorkGraphNode = {
      id: "node.low",
      title: "Low confidence",
      status: "running",
      confidence: 0.42,
    };
    const healthyNode: WorkGraphNode = {
      id: "node.healthy",
      title: "Healthy",
      status: "completed",
      confidence: 0.92,
    };

    expect(shouldShowVerifierAction(blockedNode)).toBe(true);
    expect(shouldShowVerifierAction(lowConfidenceNode)).toBe(true);
    expect(shouldShowVerifierAction(healthyNode)).toBe(false);
  });
});
