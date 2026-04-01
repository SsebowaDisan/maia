// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { parseEvidence } from "./evidence";

describe("parseEvidence", () => {
  it("prefers typed info_panel evidence_items over raw html", () => {
    const cards = parseEvidence("<p>fallback</p>", {
      userPrompt: "Use https://axongroup.com/ if needed.",
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

  it("extracts prompt URLs when structured evidence is missing", () => {
    const cards = parseEvidence("", {
      userPrompt:
        "search https://axongroup.com/ and review https://example.com/files/report.pdf",
    });

    expect(cards).toHaveLength(2);
    expect(cards[0].sourceUrl).toBe("https://axongroup.com/");
    expect(cards[0].sourceType).toBe("web");
    expect(cards[1].sourceUrl).toBe("https://example.com/files/report.pdf");
    expect(cards[1].sourceType).toBe("pdf");
  });

  it("extracts prompt file attachments when provided", () => {
    const cards = parseEvidence("", {
      promptAttachments: [
        {
          name: "Quarterly-Deck.pdf",
          fileId: "file-123",
        },
      ],
    });

    expect(cards).toHaveLength(1);
    expect(cards[0].fileId).toBe("file-123");
    expect(cards[0].source).toBe("Quarterly-Deck.pdf");
    expect(cards[0].sourceType).toBe("pdf");
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

  it("parses nested verification contract fields", () => {
    const cards = parseEvidence("", {
      infoPanel: {
        evidence_items: [
          {
            id: "evidence-4",
            source: {
              id: "src-4",
              type: "pdf",
              title: "Q4 Financials",
              file_id: "file-4",
              page: "9",
            },
            citation: {
              quote: "Operating margin expanded to 21%.",
            },
            review_location: {
              surface: "pdf",
              file_id: "file-4",
              page: "9",
            },
            highlight_target: {
              boxes: [{ x: 0.1, y: 0.12, width: 0.42, height: 0.08 }],
              unit_id: "unit-4",
              selector: "article p:nth-of-type(3)",
              char_start: 33,
              char_end: 79,
            },
            evidence_quality: {
              score: 0.81,
              tier: 3,
              confidence: 0.73,
              match_quality: "exact",
            },
          },
        ],
      },
    });

    expect(cards).toHaveLength(1);
    expect(cards[0].sourceType).toBe("pdf");
    expect(cards[0].fileId).toBe("file-4");
    expect(cards[0].page).toBe("9");
    expect(cards[0].extract).toContain("Operating margin");
    expect(cards[0].strengthScore).toBe(0.81);
    expect(cards[0].strengthTier).toBe(3);
    expect(cards[0].confidence).toBe(0.73);
    expect(cards[0].matchQuality).toBe("exact");
    expect(cards[0].unitId).toBe("unit-4");
    expect(cards[0].selector).toBe("article p:nth-of-type(3)");
    expect(cards[0].charStart).toBe(33);
    expect(cards[0].charEnd).toBe(79);
    expect(cards[0].highlightBoxes?.length).toBe(1);
  });

  it("parses sentence-level evidence units from info_html details", () => {
    const cards = parseEvidence(
      `
        <details
          class="evidence"
          id="evidence-2"
          data-file-id="file-2"
          data-page="126"
          data-evidence-units='[{"text":"CAPEX for a gigafactory-scale solid-state line is ~35% higher.","char_start":55,"char_end":120,"highlight_boxes":[{"x":0.1,"y":0.28,"width":0.52,"height":0.05}]}]'
        >
          <summary>Evidence [2]</summary>
          <div>Source: Solid-state battery benchmark</div>
          <div>Extract: CAPEX for a gigafactory-scale solid-state line is ~35% higher.</div>
        </details>
      `,
    );

    expect(cards).toHaveLength(1);
    expect(cards[0].fileId).toBe("file-2");
    expect(cards[0].page).toBe("126");
    expect(cards[0].evidenceUnits).toHaveLength(1);
    expect(cards[0].evidenceUnits?.[0]?.text).toContain("CAPEX");
    expect(cards[0].evidenceUnits?.[0]?.highlightBoxes).toHaveLength(1);
  });

  it("does not crash when evidence-unit payload exists but normalizes to empty", () => {
    const cards = parseEvidence(
      `
        <details
          class="evidence"
          id="evidence-3"
          data-file-id="file-3"
          data-evidence-units='[{"text":"too short","char_start":1,"char_end":2}]'
        >
          <summary>Evidence [3]</summary>
          <div>Source: Test</div>
          <div>Extract: This row should parse without throwing.</div>
        </details>
      `,
    );

    expect(cards).toHaveLength(1);
    expect(cards[0].id).toBe("evidence-3");
    expect(cards[0].evidenceUnits).toBeUndefined();
  });
});
