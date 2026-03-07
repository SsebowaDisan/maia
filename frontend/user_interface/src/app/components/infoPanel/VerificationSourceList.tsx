import { ExternalLink } from "lucide-react";

import type { VerificationSourceItem } from "./verificationModels";

type VerificationSourceListProps = {
  sources: VerificationSourceItem[];
  selectedSourceId: string;
  onSelectSource: (sourceId: string) => void;
};

function VerificationSourceList({ sources, selectedSourceId, onSelectSource }: VerificationSourceListProps) {
  if (!sources.length) {
    return (
      <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
        No indexed sources are available.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {sources.map((source) => {
        const active = selectedSourceId === source.id;
        return (
          <div
            key={source.id}
            className={`rounded-xl border px-3 py-2 ${active ? "border-[#0a84ff]/40 bg-[#f1f7ff]" : "border-black/[0.08] bg-white"}`}
          >
            <button type="button" onClick={() => onSelectSource(source.id)} className="w-full text-left">
              <p className="text-[12px] font-medium text-[#1d1d1f]">{source.title}</p>
              <p className="mt-0.5 text-[11px] text-[#6e6e73]">
                {source.evidenceCount} evidence • {source.kind}
              </p>
            </button>
            {source.url ? (
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-flex items-center gap-1 rounded-lg border border-black/[0.08] bg-white px-2 py-1 text-[10px] text-[#45474f] hover:bg-[#f3f4f7]"
              >
                <ExternalLink className="h-3 w-3" />
                Open source
              </a>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export { VerificationSourceList };
