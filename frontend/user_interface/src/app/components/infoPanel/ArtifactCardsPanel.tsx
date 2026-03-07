import { Copy, ExternalLink, Link2 } from "lucide-react";

import type { ArtifactRow } from "./artifactRows";

type ArtifactCardsPanelProps = {
  artifactRows: ArtifactRow[];
  onJumpToEvidence: (evidenceId: string) => void;
};

function cleanText(value: unknown): string {
  return String(value || "").trim();
}

function ArtifactCardsPanel({ artifactRows, onJumpToEvidence }: ArtifactCardsPanelProps) {
  if (artifactRows.length <= 0) {
    return (
      <div className="rounded-xl bg-[#f5f5f7] p-4 text-[12px] text-[#6e6e73]">
        No artifacts were attached for this run yet.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-[#d2d2d7] bg-white p-3 shadow-sm">
      <p className="mb-2 text-[10px] uppercase tracking-wide text-[#8e8e93]">Artifacts</p>
      <div className="space-y-2">
        {artifactRows.map((row) => {
          const sourceUrl = cleanText(row.sourceUrl);
          const evidenceId = cleanText(row.evidenceId);
          const canOpenSource = /^https?:\/\//i.test(sourceUrl);
          const canJumpEvidence = evidenceId.length > 0;
          return (
            <div key={`${row.id}-${row.title}`} className="rounded-xl border border-black/[0.08] bg-[#fafafc] p-2.5">
              <p className="text-[12px] font-medium text-[#1d1d1f]">{row.title}</p>
              {row.detail ? <p className="mt-1 text-[11px] text-[#4c4c50]">{row.detail}</p> : null}
              <div className="mt-2 inline-flex items-center gap-1 rounded-lg border border-black/[0.08] bg-white p-1">
                <button
                  type="button"
                  onClick={() => {
                    const value = sourceUrl || row.id || row.title;
                    if (!value) {
                      return;
                    }
                    void navigator.clipboard?.writeText(value);
                  }}
                  className="rounded-md p-1 text-[#6e6e73] transition hover:bg-[#f3f3f5]"
                  title="Copy artifact reference"
                >
                  <Copy className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  disabled={!canOpenSource}
                  onClick={() => {
                    if (!canOpenSource) {
                      return;
                    }
                    window.open(sourceUrl, "_blank", "noopener,noreferrer");
                  }}
                  className="rounded-md p-1 text-[#6e6e73] transition hover:bg-[#f3f3f5] disabled:opacity-40"
                  title="Open source"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  disabled={!canJumpEvidence}
                  onClick={() => {
                    if (!canJumpEvidence) {
                      return;
                    }
                    onJumpToEvidence(evidenceId);
                  }}
                  className="rounded-md p-1 text-[#6e6e73] transition hover:bg-[#f3f3f5] disabled:opacity-40"
                  title="Jump to evidence"
                >
                  <Link2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export { ArtifactCardsPanel };
