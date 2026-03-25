import { pdfjs } from "react-pdf";
import { buildAuthHeaders } from "../../../api/client/core";

type ClaimTrace = {
  id: string;
  text: string;
  evidenceRefs: number[];
};

type OutlineEntry = {
  id: string;
  title: string;
  page?: string;
  depth: number;
};

function normalizeText(raw: string): string {
  return String(raw || "").replace(/\s+/g, " ").trim();
}

function truncate(raw: string, max = 88): string {
  const cleaned = normalizeText(raw);
  if (cleaned.length <= max) {
    return cleaned;
  }
  return `${cleaned.slice(0, Math.max(0, max - 1)).trim()}...`;
}

function evidenceRefFromId(id: string): number | null {
  const match = String(id || "").match(/evidence-(\d{1,4})/i);
  if (!match?.[1]) {
    return null;
  }
  const parsed = Number.parseInt(match[1], 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseClaimTraces(assistantHtml: string): ClaimTrace[] {
  const cleanedHtml = String(assistantHtml || "").trim();
  if (!cleanedHtml) {
    return [];
  }
  const doc = new DOMParser().parseFromString(cleanedHtml, "text/html");
  const claimBlocks = Array.from(doc.querySelectorAll("p, li, h2, h3, h4"));
  const traces: ClaimTrace[] = [];
  const seen = new Set<string>();

  for (const block of claimBlocks) {
    const blockText = normalizeText(block.textContent || "");
    if (blockText.length < 28) {
      continue;
    }
    const refs = new Set<number>();
    const citationAnchors = Array.from(
      block.querySelectorAll<HTMLAnchorElement>("a.citation, a[href^='#evidence-']"),
    );
    citationAnchors.forEach((anchor) => {
      const href = String(anchor.getAttribute("href") || "");
      const hrefMatch = href.match(/#evidence-(\d{1,4})/i);
      if (hrefMatch?.[1]) {
        refs.add(Number.parseInt(hrefMatch[1], 10));
      }
      const textMatch = String(anchor.textContent || "").match(
        /(?:\[(\d{1,4})\]|【(\d{1,4})】)/,
      );
      const textRef = textMatch?.[1] || textMatch?.[2];
      if (textRef) {
        refs.add(Number.parseInt(textRef, 10));
      }
    });

    if (!refs.size) {
      for (const match of blockText.matchAll(/(?:\[(\d{1,4})\]|【(\d{1,4})】)/g)) {
        const textRef = match?.[1] || match?.[2];
        if (textRef) {
          refs.add(Number.parseInt(textRef, 10));
        }
      }
    }

    if (!refs.size) {
      continue;
    }

    const claimText = truncate(
      blockText.replace(/(?:\[\d{1,4}\]|【\d{1,4}】)/g, "").trim(),
      130,
    );
    if (!claimText) {
      continue;
    }
    const dedupeKey = `${claimText.toLowerCase()}::${Array.from(refs).sort((a, b) => a - b).join(",")}`;
    if (seen.has(dedupeKey)) {
      continue;
    }
    seen.add(dedupeKey);
    traces.push({
      id: `claim-${traces.length + 1}`,
      text: claimText,
      evidenceRefs: Array.from(refs).filter((value) => Number.isFinite(value)).sort((a, b) => a - b),
    });
    if (traces.length >= 10) {
      break;
    }
  }
  return traces;
}

async function resolveDestinationPage(pdfDocument: any, destination: unknown): Promise<number | undefined> {
  if (!destination) {
    return undefined;
  }
  let explicitDestination = destination;
  if (typeof destination === "string") {
    explicitDestination = await pdfDocument.getDestination(destination);
  }
  if (!Array.isArray(explicitDestination) || !explicitDestination.length) {
    return undefined;
  }

  const target = explicitDestination[0];
  if (typeof target === "object" && target !== null) {
    try {
      const pageIndex = await pdfDocument.getPageIndex(target);
      if (Number.isFinite(pageIndex) && pageIndex >= 0) {
        return pageIndex + 1;
      }
    } catch {
      return undefined;
    }
  }
  if (typeof target === "number" && Number.isFinite(target) && target >= 0) {
    return target + 1;
  }
  return undefined;
}

async function flattenOutlineItems(
  pdfDocument: any,
  items: any[],
  depth = 0,
  rows: OutlineEntry[] = [],
): Promise<OutlineEntry[]> {
  for (const item of items) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const title = truncate(String(item.title || "Section"), 52);
    if (title) {
      const pageNumber = await resolveDestinationPage(pdfDocument, item.dest);
      rows.push({
        id: `outline-${rows.length + 1}`,
        title,
        page: pageNumber ? String(pageNumber) : undefined,
        depth,
      });
      if (rows.length >= 80) {
        return rows;
      }
    }
    const children = Array.isArray(item.items) ? item.items : [];
    if (children.length) {
      await flattenOutlineItems(pdfDocument, children, Math.min(depth + 1, 4), rows);
      if (rows.length >= 80) {
        return rows;
      }
    }
  }
  return rows;
}

async function loadPdfOutline(fileUrl: string): Promise<OutlineEntry[]> {
  const headers = buildAuthHeaders();
  const task = pdfjs.getDocument({
    url: fileUrl,
    ...(Object.keys(headers).length > 0 ? { httpHeaders: headers } : {}),
  });
  const pdfDocument = await task.promise;
  try {
    const outline = await pdfDocument.getOutline();
    if (!Array.isArray(outline)) {
      return [];
    }
    return (await flattenOutlineItems(pdfDocument, outline)).slice(0, 40);
  } finally {
    await pdfDocument.destroy();
  }
}

function rowPositions(count: number, y: number, baseGap = 230): Array<{ x: number; y: number }> {
  if (count <= 0) {
    return [];
  }
  if (count === 1) {
    return [{ x: 140, y }];
  }
  const gap = Math.max(180, baseGap - Math.min(90, count * 6));
  const startX = 40;
  return Array.from({ length: count }, (_, index) => ({
    x: startX + index * gap,
    y,
  }));
}

export {
  evidenceRefFromId,
  loadPdfOutline,
  normalizeText,
  parseClaimTraces,
  rowPositions,
  truncate,
  type ClaimTrace,
  type OutlineEntry,
};
