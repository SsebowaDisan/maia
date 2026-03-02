import { normalizeText, plainText } from "./text";
import type { EvidenceCard } from "./types";

function parseEvidence(infoHtml: string): EvidenceCard[] {
  if (!infoHtml.trim()) {
    return [];
  }

  const doc = new DOMParser().parseFromString(infoHtml, "text/html");
  const detailsNodes = Array.from(doc.querySelectorAll("details.evidence"));
  if (!detailsNodes.length) {
    const fallback = plainText(infoHtml);
    return fallback
      ? [
          {
            id: "evidence-1",
            title: "Evidence",
            source: "Indexed context",
            extract: fallback,
          },
        ]
      : [];
  }

  return detailsNodes.map((details, index) => {
    const detailsId = (details.getAttribute("id") || "").trim();
    const summary = normalizeText(
      details.querySelector("summary")?.textContent || `Evidence ${index + 1}`,
    );

    let source = "";
    let extract = "";
    const divs = Array.from(details.querySelectorAll("div"));
    for (const div of divs) {
      const text = normalizeText(div.textContent || "");
      if (!source && /^source\s*:/i.test(text)) {
        source = text.replace(/^source\s*:/i, "").trim();
      }
      if (!extract && /^extract\s*:/i.test(text)) {
        extract = text.replace(/^extract\s*:/i, "").trim();
      }
    }

    if (!extract) {
      const evidenceContent = details.querySelector(".evidence-content");
      extract = normalizeText(evidenceContent?.textContent || "");
    }
    if (!extract) {
      extract = normalizeText(details.textContent || "");
    }
    if (!source) {
      source = "Indexed source";
    }

    const imageSrc = details.querySelector("img")?.getAttribute("src") || undefined;
    const pageAttr = (details.getAttribute("data-page") || "").trim();
    const pageMatch = summary.match(/page\s+(\d+)/i);
    const fileId = (details.getAttribute("data-file-id") || "").trim() || undefined;

    return {
      id: detailsId || `evidence-${index + 1}`,
      title: summary,
      source,
      page: pageAttr || pageMatch?.[1],
      fileId,
      extract,
      imageSrc,
    };
  });
}

export { parseEvidence };
