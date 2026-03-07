import { FileImage, FileText, Globe, Layers } from "lucide-react";

import type { VerificationSourceItem } from "./verificationModels";

type VerificationSourceBarProps = {
  sources: VerificationSourceItem[];
  selectedSourceId: string;
  onSelectSource: (sourceId: string) => void;
};

function kindIcon(kind: VerificationSourceItem["kind"]) {
  if (kind === "pdf") {
    return <FileText className="h-3.5 w-3.5 text-[#3a3a3c]" />;
  }
  if (kind === "web") {
    return <Globe className="h-3.5 w-3.5 text-[#3a3a3c]" />;
  }
  if (kind === "image") {
    return <FileImage className="h-3.5 w-3.5 text-[#3a3a3c]" />;
  }
  return <Layers className="h-3.5 w-3.5 text-[#3a3a3c]" />;
}

function statusLabel(status: VerificationSourceItem["status"]): string {
  if (status === "loading") {
    return "loading";
  }
  if (status === "evidence_found") {
    return "evidence";
  }
  return "ready";
}

function VerificationSourceBar({ sources, selectedSourceId, onSelectSource }: VerificationSourceBarProps) {
  if (!sources.length) {
    return (
      <div className="rounded-xl border border-black/[0.06] bg-white px-3 py-2 text-[12px] text-[#6e6e73]">
        No sources available yet.
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-2xl border border-[#d2d2d7] bg-white px-3 py-3 shadow-sm">
      <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Sources</p>
      <div className="flex gap-2 overflow-x-auto pb-0.5">
        {sources.map((source) => {
          const selected = source.id === selectedSourceId;
          return (
            <button
              key={source.id}
              type="button"
              onClick={() => onSelectSource(source.id)}
              className={`min-w-[168px] shrink-0 rounded-xl border px-2.5 py-2 text-left transition ${
                selected
                  ? "border-[#111827]/25 bg-[#f6f7fb]"
                  : "border-black/[0.08] bg-white hover:bg-[#f6f7fb]"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg border border-black/[0.08] bg-[#f2f2f7]">
                  {kindIcon(source.kind)}
                </span>
                <span className="rounded-full border border-black/[0.08] bg-white px-1.5 py-0.5 text-[10px] text-[#6e6e73]">
                  {source.evidenceCount}
                </span>
              </div>
              <p className="mt-1.5 truncate text-[12px] font-medium text-[#1d1d1f]" title={source.title}>
                {source.title}
              </p>
              <p className="mt-1 text-[10px] uppercase tracking-wide text-[#8e8e93]">{statusLabel(source.status)}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export { VerificationSourceBar };
