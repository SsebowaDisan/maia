import { X } from "lucide-react";
import type { FocusNodePayload, MindmapMapType, MindmapNode } from "./types";
import { describeMindmapMapType } from "./presentation";
import { resolveProfessionalNodeTitle } from "./titleSanitizer";

type MindMapViewerDetailsProps = {
  activeMapType: MindmapMapType;
  selectedNode: MindmapNode | null;
  childNodes?: MindmapNode[];
  onAskNode?: (payload: FocusNodePayload) => void;
  onFocusBranch?: (nodeId: string | null) => void;
  isFocusActive?: boolean;
  canvasMode?: boolean;
  onClose?: () => void;
};

function normalizeHttpUrl(value: string): string {
  const raw = String(value || "").replace(/&amp;/gi, "&").trim();
  if (!raw) {
    return "";
  }
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return "";
    }
    return parsed.toString();
  } catch {
    return "";
  }
}

function collectSourceLinks(value: string): string[] {
  const raw = String(value || "");
  if (!raw) {
    return [];
  }
  const urls = new Set<string>();
  const patterns = [
    /data-source-url\s*=\s*["']([^"']+)["']/gi,
    /data-viewer-url\s*=\s*["']([^"']+)["']/gi,
    /href\s*=\s*["'](https?:\/\/[^"']+)["']/gi,
    /(https?:\/\/[^\s"'<>]+)/gi,
  ];
  patterns.forEach((pattern) => {
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(raw)) !== null) {
      const normalized = normalizeHttpUrl(match[1] || match[0] || "");
      if (normalized) {
        urls.add(normalized);
      }
    }
  });
  return Array.from(urls).slice(0, 8);
}

function linkLabel(url: string): string {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./i, "");
    const path = parsed.pathname && parsed.pathname !== "/" ? parsed.pathname : "";
    const label = `${host}${path}`;
    return label.length > 64 ? `${label.slice(0, 64)}...` : label;
  } catch {
    return url;
  }
}

function cleanDetailText(value: string): string {
  return String(value || "")
    .replace(/<a\b[^>]*>([\s\S]*?)<\/a>/gi, "$1")
    .replace(/<\/?[^>]+>/g, " ")
    .replace(/\b(?:href|id|class|target|rel|title|data-[a-z-]+)\s*=\s*(["']).*?\1/gi, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\s+#{1,6}\s+/g, " ")
    .replace(/(\[\d+\])\s*\1+/g, "$1")
    .replace(/\r?\n+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/(?:\.\.\.)+\s*$/g, "")
    .trim();
}

function toReadableSentence(value: string): string {
  const text = cleanDetailText(value);
  if (!text) {
    return "";
  }
  if (/[.!?]$/.test(text)) {
    return text;
  }
  return `${text}.`;
}

function toSummarySegments(value: string): string[] {
  const normalized = cleanDetailText(value)
    .replace(/\s*[\u2022\u00b7\u25aa\u25e6]\s*/g, "\n")
    .replace(/\s*\|\s*/g, "\n")
    .replace(/\s*;\s*/g, "\n")
    .replace(/\r?\n+/g, "\n")
    .trim();
  if (!normalized) {
    return [];
  }

  const rows = normalized
    .split("\n")
    .map((row) => row.replace(/^[\-*]+/, "").trim())
    .map((row) => row.replace(/(?:\[\d+\]\s*)+/g, "").trim())
    .map((row) => toReadableSentence(row))
    .filter(Boolean);

  return rows.filter((row, index, arr) => arr.indexOf(row) === index);
}

function renderTextWithLinks(value: string): Array<string | JSX.Element> {
  const text = String(value || "");
  if (!text) {
    return [];
  }
  const regex = /(https?:\/\/[^\s)]+(?:\([^\s)]*\))?)/gi;
  const result: Array<string | JSX.Element> = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let idx = 0;
  while ((match = regex.exec(text)) !== null) {
    const start = match.index;
    const end = regex.lastIndex;
    if (start > lastIndex) {
      result.push(text.slice(lastIndex, start));
    }
    const normalized = normalizeHttpUrl(match[0] || "");
    if (normalized) {
      result.push(
        <a
          key={`${normalized}-${idx}`}
          href={normalized}
          target="_blank"
          rel="noreferrer"
          className="text-[#1d4ed8] underline decoration-[#1d4ed8]/35 underline-offset-2 transition-colors hover:text-[#1e40af]"
        >
          {linkLabel(normalized)}
        </a>,
      );
      idx += 1;
    } else {
      result.push(match[0]);
    }
    lastIndex = end;
  }
  if (lastIndex < text.length) {
    result.push(text.slice(lastIndex));
  }
  return result;
}

function toFocusPayload(node: MindmapNode): FocusNodePayload {
  const cleanedNodeText = cleanDetailText(node.text || node.summary || "");
  return {
    nodeId: node.id,
    title: resolveProfessionalNodeTitle(node),
    text: cleanedNodeText,
    pageRef: node.page_ref || node.page || undefined,
    sourceId: node.source_id,
    sourceName: node.source_name,
  };
}

export function MindMapViewerDetails({
  activeMapType,
  selectedNode,
  childNodes = [],
  onAskNode,
  onFocusBranch,
  isFocusActive = false,
  canvasMode = false,
  onClose,
}: MindMapViewerDetailsProps) {
  const mapCopy = describeMindmapMapType(activeMapType);
  const shellClass = canvasMode
    ? "flex h-full flex-col overflow-hidden rounded-[18px] border border-white/55 bg-[linear-gradient(180deg,rgba(255,255,255,0.84),rgba(250,251,255,0.72))] shadow-[0_16px_36px_rgba(15,23,42,0.14)] backdrop-blur-xl"
    : "flex h-full flex-col overflow-hidden rounded-[20px] border border-white/80 bg-white/84 shadow-[0_14px_32px_rgba(15,23,42,0.12)] backdrop-blur-xl";
  const footerClass = canvasMode
    ? "border-t border-black/[0.05] bg-white/45 px-5 py-4"
    : "border-t border-black/[0.06] bg-white/65 px-5 py-4";
  const actionClass = canvasMode
    ? "border-t border-black/[0.05] bg-white/45 px-5 py-5"
    : "border-t border-black/[0.06] bg-white/65 px-5 py-5";

  if (!selectedNode) {
    return (
      <div className={shellClass}>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
              Node details
            </p>
            {onClose ? (
              <button
                type="button"
                onClick={onClose}
                className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-black/[0.06] bg-white/85 text-[#6b7280] transition-colors hover:bg-white hover:text-[#17171b]"
                title="Hide details"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
          <h4 className="mt-2 text-[18px] font-semibold tracking-[-0.03em] text-[#17171b]">
            Select a branch
          </h4>
          <p className="mt-2 text-[13px] leading-6 text-[#61636c]">
            This side panel stays stable while you explore the map. Select a node to inspect its summary
            and follow-up actions.
          </p>
          <div className="mt-5 rounded-[16px] border border-dashed border-black/[0.08] bg-white/68 px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
              Current map
            </p>
            <p className="mt-2 text-[15px] font-semibold text-[#17171b]">{mapCopy.label}</p>
            <p className="mt-1 text-[12px] leading-5 text-[#6b6b70]">{mapCopy.summary}</p>
          </div>
        </div>
        <div className={footerClass}>
          <p className="text-[11px] leading-5 text-[#777b86]">
            Branch actions appear here once you select part of the map.
          </p>
        </div>
      </div>
    );
  }

  const text = String(selectedNode.text || selectedNode.summary || "").trim();
  const sourceLinks = collectSourceLinks(text);
  const displayTitle = resolveProfessionalNodeTitle(selectedNode);
  const isSyntheticGroup = Boolean(selectedNode.synthetic);
  const summarySegments = toSummarySegments(text);
  const summaryLead = summarySegments[0] || "";
  const summaryBullets = summarySegments.slice(1, 8);
  const childTitles = childNodes
    .map((node) => resolveProfessionalNodeTitle(node))
    .filter((title) => String(title || "").trim().length > 0)
    .filter((title, index, arr) => arr.indexOf(title) === index)
    .slice(0, 8);

  return (
    <div className={shellClass}>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <div className="flex items-start justify-between gap-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
            Selected node
          </p>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-black/[0.06] bg-white/85 text-[#6b7280] transition-colors hover:bg-white hover:text-[#17171b]"
              title="Hide details"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
        <h4 className="mt-2 text-[20px] font-semibold tracking-[-0.03em] text-[#17171b]">
          {displayTitle}
        </h4>
        {summaryLead ? (
          <p className="mt-3 text-[13px] leading-6 text-[#61636c]">{renderTextWithLinks(summaryLead)}</p>
        ) : null}
        {summaryBullets.length > 0 ? (
          <ul className="mt-2 list-disc space-y-1.5 pl-4">
            {summaryBullets.map((line) => (
              <li key={line} className="text-[12px] leading-5 text-[#5f6470]">
                {renderTextWithLinks(line)}
              </li>
            ))}
          </ul>
        ) : null}
        {sourceLinks.length > 0 ? (
          <div className="mt-4 border-t border-black/[0.05] pt-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[#7b8598]">
              References
            </p>
            <ul className="mt-2 space-y-1.5">
              {sourceLinks.map((url) => (
                <li key={url} className="text-[12px] leading-5">
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[#1d4ed8] underline decoration-[#1d4ed8]/35 underline-offset-2 transition-colors hover:text-[#1e40af]"
                  >
                    {linkLabel(url)}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {childTitles.length > 0 ? (
          <div className="mt-4 border-t border-black/[0.05] pt-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[#7b8598]">
              Connected branches
            </p>
            <ul className="mt-2 space-y-1.5">
              {childTitles.map((title) => (
                <li key={title} className="text-[12px] leading-5 text-[#5f6470]">
                  {title}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {onFocusBranch || (onAskNode && !isSyntheticGroup) ? (
        <div className={actionClass}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
            Actions
          </p>
          <div className="mt-3 flex flex-col gap-2">
            {onFocusBranch ? (
              <button
                type="button"
                onClick={() => onFocusBranch(isFocusActive ? null : selectedNode.id)}
                className={`inline-flex h-11 items-center justify-center rounded-full border px-4 text-[13px] font-semibold transition-colors ${
                  isFocusActive
                    ? "border-[#3b82f6]/30 bg-[#eff6ff] text-[#1d4ed8] hover:bg-[#dbeafe]"
                    : "border-black/[0.08] bg-[#fafaf7] text-[#17171b] hover:bg-[#f3f3f0]"
                }`}
              >
                {isFocusActive ? "Unfocus branch" : "Focus branch"}
              </button>
            ) : null}
            {onAskNode && !isSyntheticGroup ? (
              <button
                type="button"
                onClick={() => onAskNode(toFocusPayload(selectedNode))}
                className="inline-flex h-11 items-center justify-center rounded-full bg-[#17171b] px-4 text-[13px] font-semibold text-white transition-colors hover:bg-[#2a2a30]"
              >
                Ask about this node
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

