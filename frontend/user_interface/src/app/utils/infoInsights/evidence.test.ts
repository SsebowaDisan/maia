import { describe, expect, it } from "vitest";

import { parseEvidence } from "./evidence";

describe("parseEvidence", () => {
  it("prefers typed info_panel evidence_items over raw html", () => {
    const cards = parseEvidence("<p>fallback</p>", {
      infoPanel: {
        evidence_items: [
          {
            id: "evidence-12",
            title: "Evidence [12]",
            source_type: "web",
            source_name: "Axon Group | About",
            source_url: "https://axongroup.com/about-axon",
            page: "3",
            extract: "Axon Group is family-owned.",
            graph_node_ids: ["node-1"],
            scene_refs: ["scene.browser.main"],
            event_refs: ["evt-77"],
          },
        ],
      },
    });

    expect(cards).toHaveLength(1);
    expect(cards[0].id).toBe("evidence-12");
    expect(cards[0].sourceType).toBe("web");
    expect(cards[0].graphNodeIds).toEqual(["node-1"]);
    expect(cards[0].sceneRefs).toEqual(["scene.browser.main"]);
    expect(cards[0].eventRefs).toEqual(["evt-77"]);
  });

  it("keeps deep-link and confidence fields from typed evidence payload", () => {
    const cards = parseEvidence("", {
      infoPanel: {
        evidence_items: [
          {
            id: "evidence-1",
            source_type: "pdf",
            source_name: "Quarterly report",
            extract: "Revenue rose 14%.",
            confidence: 0.7,
            collected_by: "agent.document",
            graph_node_ids: ["node-5"],
            scene_refs: ["scene.pdf.reader"],
            event_refs: ["evt-5"],
          },
        ],
      },
    });

    expect(cards).toHaveLength(1);
    expect(cards[0].sourceType).toBe("pdf");
    expect(cards[0].confidence).toBe(0.7);
    expect(cards[0].collectedBy).toBe("agent.document");
    expect(cards[0].graphNodeIds).toEqual(["node-5"]);
    expect(cards[0].sceneRefs).toEqual(["scene.pdf.reader"]);
    expect(cards[0].eventRefs).toEqual(["evt-5"]);
  });
});
