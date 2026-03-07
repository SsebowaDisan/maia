import { SkipBack, SkipForward } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { CitationFocus } from "../../types";
import type { WorkspaceRenderMode } from "./workspaceRenderModes";
import type { WorkspaceRailTab } from "./workspaceRailTabs";

type WorkspaceTimelineDockProps = {
  activeTab: WorkspaceRailTab;
  citationFocus: CitationFocus | null;
  onSelectCitationFocus?: (citation: CitationFocus) => void;
  workspaceRenderMode: WorkspaceRenderMode;
};

function normalizeRefs(raw: unknown): string[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const rows = raw
    .map((item) => String(item || "").trim())
    .filter((item) => item.length > 0);
  return Array.from(new Set(rows)).slice(0, 48);
}

function WorkspaceTimelineDock({
  activeTab,
  citationFocus,
  onSelectCitationFocus,
  workspaceRenderMode,
}: WorkspaceTimelineDockProps) {
  const eventRefs = useMemo(() => normalizeRefs(citationFocus?.eventRefs), [citationFocus?.eventRefs]);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    setCursor(0);
  }, [eventRefs.join("|"), citationFocus?.evidenceId, citationFocus?.sourceName]);

  if (!citationFocus) {
    return null;
  }

  const boundedCursor = Math.max(0, Math.min(eventRefs.length - 1, cursor));
  const canStep = eventRefs.length > 1;
  const selectedEventRef = eventRefs[boundedCursor] || "";

  const jumpToSelectedRef = () => {
    if (!selectedEventRef || !onSelectCitationFocus) {
      return;
    }
    onSelectCitationFocus({
      ...citationFocus,
      eventRefs: [selectedEventRef],
    });
  };

  return (
    <div className="border-t border-black/[0.06] bg-white/95 px-5 py-2.5">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Timeline dock</p>
          <p className="truncate text-[11px] text-[#4c4c50]">
            {activeTab.replace("_", " ")} {selectedEventRef ? `- ${selectedEventRef}` : "- no event refs"}
          </p>
        </div>
        <div className="inline-flex items-center gap-1 rounded-xl border border-black/[0.08] bg-[#fafafc] p-1">
          {workspaceRenderMode !== "fast" ? (
            <button
              type="button"
              disabled={!canStep}
              onClick={() => setCursor((previous) => Math.max(0, previous - 1))}
              className="rounded-lg p-1.5 text-[#6e6e73] transition hover:bg-white disabled:opacity-40"
              title="Previous timeline event"
            >
              <SkipBack className="h-3.5 w-3.5" />
            </button>
          ) : null}
          <button
            type="button"
            onClick={jumpToSelectedRef}
            disabled={!selectedEventRef || !onSelectCitationFocus}
            className="rounded-lg border border-black/[0.08] bg-white px-2 py-1 text-[11px] text-[#1d1d1f] transition hover:bg-[#f3f3f5] disabled:opacity-40"
            title="Jump replay to selected event reference"
          >
            Jump
          </button>
          {workspaceRenderMode !== "fast" ? (
            <button
              type="button"
              disabled={!canStep}
              onClick={() => setCursor((previous) => Math.min(eventRefs.length - 1, previous + 1))}
              className="rounded-lg p-1.5 text-[#6e6e73] transition hover:bg-white disabled:opacity-40"
              title="Next timeline event"
            >
              <SkipForward className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export { WorkspaceTimelineDock };
