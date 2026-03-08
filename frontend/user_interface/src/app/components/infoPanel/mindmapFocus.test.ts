import { describe, expect, it } from "vitest";

import type { FocusNodePayload } from "../mindmapViewer/types";
import type { EvidenceCard } from "../../utils/infoInsights";
import type { VerificationSourceItem } from "./verificationModels";
import { resolveMindmapFocus } from "./mindmapFocus";

describe("resolveMindmapFocus", () => {
  const sources: VerificationSourceItem[] = [
    {
      id: "url:https://axongroup.com/about-axon",
      title: "Axon Group | About",
      kind: "web",
      status: "evidence_found",
      url: "https://axongroup.com/about-axon",
      evidenceCount: 2,
      citedCount: 2,
      maxStrengthScore: 0.8,
    },
  ];

  const evidenceBySource: Record<string, EvidenceCard[]> = {
    "url:https://axongroup.com/about-axon": [
      {
        id: "evidence-1",
        title: "Evidence [1]",
        source: "Axon Group | About",
        extract: "Axon Group is family-owned and active in six domains.",
        page: "3",
      },
      {
        id: "evidence-2",
        title: "Evidence [2]",
        source: "Axon Group | About",
        extract: "The company has more than 50 years of experience.",
        page: "2",
      },
    ],
  };

  it("resolves by explicit source id and best text overlap", () => {
    const node: FocusNodePayload = {
      nodeId: "node-1",
      title: "Family-owned company",
      text: "Find evidence for family ownership",
      sourceId: "url:https://axongroup.com/about-axon",
    };
    const result = resolveMindmapFocus({
      node,
      sources,
      evidenceBySource,
    });
    expect(result.sourceId).toBe("url:https://axongroup.com/about-axon");
    expect(result.evidenceCard?.id).toBe("evidence-1");
  });

  it("resolves source by source name and page hint", () => {
    const node: FocusNodePayload = {
      nodeId: "node-2",
      title: "Company experience",
      text: "Years of operation",
      sourceName: "Axon Group | About",
      pageRef: "2",
    };
    const result = resolveMindmapFocus({
      node,
      sources,
      evidenceBySource,
    });
    expect(result.sourceId).toBe("url:https://axongroup.com/about-axon");
    expect(result.evidenceCard?.id).toBe("evidence-2");
  });
});
