import { describe, expect, it } from "vitest";

import { formatSceneSummary, summarizeConnectorCapabilities } from "./pluginCapabilities";

describe("pluginCapabilities", () => {
  it("summarizes actions, evidence emitters, graph mappings, and scenes", () => {
    const summaries = summarizeConnectorCapabilities([
      {
        connector_id: "gmail",
        label: "Gmail",
        enabled: true,
        actions: [
          {
            action_id: "email.send",
            title: "Send email",
            description: "",
            event_family: "email",
            scene_type: "email",
            tool_ids: [],
          },
          {
            action_id: "email.search",
            title: "Search inbox",
            description: "",
            event_family: "email",
            scene_type: "email",
            tool_ids: [],
          },
        ],
        evidence_emitters: [{ emitter_id: "gmail.thread", source_type: "email", fields: ["thread_id"] }],
        scene_mapping: [{ scene_type: "email", action_ids: ["email.send", "email.search"] }],
        graph_mapping: [{ action_id: "email.send", node_type: "email_draft", edge_family: "sequential" }],
      },
    ]);
    const gmail = summaries.gmail;
    expect(gmail).toBeTruthy();
    expect(gmail.actionCount).toBe(2);
    expect(gmail.evidenceEmitterCount).toBe(1);
    expect(gmail.graphMappingCount).toBe(1);
    expect(gmail.sceneTypes).toEqual(["email"]);
    expect(gmail.featuredActions).toEqual(["Send email", "Search inbox"]);
  });

  it("formats scene summary with a fallback for empty lists", () => {
    expect(formatSceneSummary(["api", "browser"])).toBe("api, browser");
    expect(formatSceneSummary([])).toBe("system");
  });
});
