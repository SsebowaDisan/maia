import { describe, expect, it } from "vitest";

import { deriveIngestionJobProgress, formatIngestionJobProgress } from "./ingestionProgress";

describe("ingestionProgress", () => {
  it("surfaces OCR work for heavy PDF jobs", () => {
    const progress = deriveIngestionJobProgress({
      kind: "files",
      status: "running",
      total_items: 1,
      processed_items: 0,
      bytes_total: 100,
      bytes_indexed: 12,
      debug: [
        "report.pdf: pdf route=heavy (reason=heavy-image-ratio, image_ratio=0.900, low_text_ratio=0.820).",
      ],
    });

    expect(progress.currentStep).toBe("Running OCR");
    expect(progress.remainingSteps).toContain("Indexing for answers");
    expect(progress.explanation).toContain("OCR route");
  });

  it("shows finalizing when page-unit precompute is scheduled", () => {
    const progress = deriveIngestionJobProgress({
      kind: "files",
      status: "running",
      total_items: 1,
      processed_items: 1,
      bytes_total: 100,
      bytes_indexed: 100,
      debug: ["report.pdf: scheduled page-unit precompute."],
    });

    expect(progress.currentStep).toBe("Finalizing");
    expect(progress.remainingSteps).toEqual(["Ready"]);
    expect(progress.explanation).toContain("citations");
  });

  it("formats remaining steps for active jobs", () => {
    const label = formatIngestionJobProgress({
      kind: "files",
      status: "running",
      total_items: 2,
      processed_items: 1,
      bytes_total: 200,
      bytes_indexed: 80,
      debug: ["Indexing [1/2]: brief.pdf"],
    });

    expect(label).toContain("Indexing for answers");
    expect(label).toContain("Remaining:");
    expect(label).toContain("Finalizing");
  });
});
