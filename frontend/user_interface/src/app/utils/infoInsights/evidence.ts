import { normalizeText, plainText } from "./text";
import type { EvidenceCard, HighlightBox } from "./types";

function toFiniteNumber(value: unknown): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
}

function clamp01(value: number): number {
  if (value < 0) {
    return 0;
  }
  if (value > 1) {
    return 1;
  }
  return value;
}

function normalizeHighlightBox(raw: unknown): HighlightBox | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const x = toFiniteNumber(record.x);
  const y = toFiniteNumber(record.y);
  const width = toFiniteNumber(record.width);
  const height = toFiniteNumber(record.height);
  if (x === null || y === null || width === null || height === null) {
    return null;
  }
  const nx = clamp01(x);
  const ny = clamp01(y);
  const nw = Math.max(0, Math.min(1 - nx, width));
  const nh = Math.max(0, Math.min(1 - ny, height));
  if (nw < 0.002 || nh < 0.002) {
    return null;
  }
  return {
    x: Number(nx.toFixed(6)),
    y: Number(ny.toFixed(6)),
    width: Number(nw.toFixed(6)),
    height: Number(nh.toFixed(6)),
  };
}

function parseHighlightBoxes(raw: string | null): HighlightBox[] {
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    const boxes: HighlightBox[] = [];
    for (const row of parsed) {
      const normalized = normalizeHighlightBox(row);
      if (!normalized) {
        continue;
      }
      boxes.push(normalized);
      if (boxes.length >= 24) {
        break;
      }
    }
    return boxes;
  } catch {
    return [];
  }
}

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
    const highlightBoxes = parseHighlightBoxes(details.getAttribute("data-boxes"));

    return {
      id: detailsId || `evidence-${index + 1}`,
      title: summary,
      source,
      page: pageAttr || pageMatch?.[1],
      fileId,
      extract,
      imageSrc,
      highlightBoxes: highlightBoxes.length ? highlightBoxes : undefined,
    };
  });
}

export { parseEvidence };
