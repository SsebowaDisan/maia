import type { FocusNodePayload, MindmapMapType, MindmapNode } from "./types";
import { describeMindmapMapType } from "./presentation";
import { resolveProfessionalNodeTitle } from "./titleSanitizer";

type MindMapViewerDetailsProps = {
  activeMapType: MindmapMapType;
  selectedNode: MindmapNode | null;
  onAskNode?: (payload: FocusNodePayload) => void;
  onFocusBranch?: (nodeId: string | null) => void;
  isFocusActive?: boolean;
};

function metaChip(label: string, value: string | number | null | undefined) {
  const text = String(value ?? "").trim();
  if (!text) {
    return null;
  }
  return (
    <span
      key={`${label}-${text}`}
      className="inline-flex items-center rounded-full border border-black/[0.06] bg-[#fafaf7] px-2.5 py-1 text-[11px] font-medium text-[#4a4a50]"
    >
      {label}: {text}
    </span>
  );
}

function toFocusPayload(node: MindmapNode): FocusNodePayload {
  return {
    nodeId: node.id,
    title: node.title || "",
    text: node.text || node.summary || "",
    pageRef: node.page_ref || node.page || undefined,
    sourceId: node.source_id,
    sourceName: node.source_name,
  };
}

export function MindMapViewerDetails({
  activeMapType,
  selectedNode,
  onAskNode,
  onFocusBranch,
  isFocusActive = false,
}: MindMapViewerDetailsProps) {
  const mapCopy = describeMindmapMapType(activeMapType);

  if (!selectedNode) {
    return (
      <div className="overflow-hidden rounded-[22px] border border-black/[0.06] bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
        <div className="px-5 py-5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
          Node details
        </p>
        <h4 className="mt-2 text-[18px] font-semibold tracking-[-0.03em] text-[#17171b]">
          Select a branch
        </h4>
        <p className="mt-2 text-[13px] leading-6 text-[#61636c]">
          This side panel stays stable while you explore the map. Select a node to inspect its summary,
          metadata, and follow-up actions.
        </p>
        <div className="mt-5 rounded-[18px] border border-dashed border-black/[0.08] bg-[#fbfbf8] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
            Current map
          </p>
          <p className="mt-2 text-[15px] font-semibold text-[#17171b]">{mapCopy.label}</p>
          <p className="mt-1 text-[12px] leading-5 text-[#6b6b70]">{mapCopy.summary}</p>
        </div>
        </div>
        <div className="border-t border-black/[0.05] bg-[linear-gradient(180deg,#ffffff_0%,#f8f7f3_100%)] px-5 py-4">
          <p className="text-[11px] leading-5 text-[#777b86]">
            Branch actions appear here once you select part of the map.
          </p>
        </div>
      </div>
    );
  }

  const text = String(selectedNode.text || selectedNode.summary || "").trim();
  const displayTitle = resolveProfessionalNodeTitle(selectedNode);
  const isSyntheticGroup = Boolean(selectedNode.synthetic);
  const confidence = Number(selectedNode.confidence);
  const confidenceLabel = Number.isFinite(confidence) ? `${Math.round(confidence * 100)}%` : null;
  const chips = [
    metaChip("Type", selectedNode.node_type || selectedNode.type || null),
    metaChip("Page", selectedNode.page_ref || selectedNode.page || null),
    metaChip("Source", selectedNode.source_name || selectedNode.source_id || null),
    metaChip("Status", selectedNode.status || null),
    metaChip("Confidence", confidenceLabel),
    metaChip("Sources", selectedNode.source_count),
    metaChip("Citations", selectedNode.citation_count),
  ].filter(Boolean);

  return (
    <div className="overflow-hidden rounded-[22px] border border-black/[0.06] bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="px-5 py-5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
        Selected node
      </p>
      <h4 className="mt-2 text-[20px] font-semibold tracking-[-0.03em] text-[#17171b]">
        {displayTitle}
      </h4>
      <p className="mt-3 text-[13px] leading-6 text-[#61636c]">
        {text || "No node summary was provided by the backend for this branch yet."}
      </p>
      {chips.length > 0 ? <div className="mt-4 flex flex-wrap gap-2">{chips}</div> : null}
      </div>

      {onFocusBranch || (onAskNode && !isSyntheticGroup) ? (
        <div className="border-t border-black/[0.06] bg-[linear-gradient(180deg,#ffffff_0%,#f8f7f3_100%)] px-5 py-5">
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
