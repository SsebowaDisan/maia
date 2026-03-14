import { useMemo, useState } from "react";

type MemoryEpisode = {
  id: string;
  summary: string;
  createdAt: string;
};

type MemoryExplorerProps = {
  episodes: MemoryEpisode[];
  onDeleteEpisode?: (episodeId: string) => void;
};

type MemoryTab = "episodes" | "knowledge" | "working";

export function MemoryExplorer({ episodes, onDeleteEpisode }: MemoryExplorerProps) {
  const [activeTab, setActiveTab] = useState<MemoryTab>("episodes");
  const [query, setQuery] = useState("open opportunities in healthcare");
  const simulatedKnowledge = useMemo(
    () => [
      `Top documents matching "${query}"`,
      "Quarterly pipeline report - healthcare segment",
      "Retention analysis notes - enterprise accounts",
    ],
    [query],
  );

  return (
    <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-3 flex items-center gap-2">
        {(["episodes", "knowledge", "working"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`rounded-full px-3 py-1.5 text-[12px] font-semibold capitalize ${
              activeTab === tab ? "bg-[#111827] text-white" : "bg-[#f2f4f7] text-[#475467]"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "episodes" ? (
        <div className="space-y-2">
          {episodes.map((episode) => (
            <div key={episode.id} className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3">
              <p className="text-[13px] font-semibold text-[#111827]">{episode.summary}</p>
              <div className="mt-1 flex items-center justify-between">
                <p className="text-[12px] text-[#667085]">{new Date(episode.createdAt).toLocaleString()}</p>
                <button
                  type="button"
                  onClick={() => onDeleteEpisode?.(episode.id)}
                  className="text-[12px] font-semibold text-[#b42318] hover:underline"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {activeTab === "knowledge" ? (
        <div>
          <label className="block text-[12px] font-semibold text-[#667085]">Recall query</label>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
          />
          <ul className="mt-3 list-disc space-y-1 pl-4 text-[13px] text-[#475467]">
            {simulatedKnowledge.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {activeTab === "working" ? (
        <div className="rounded-xl border border-black/[0.06] bg-[#f8fafc] p-3 text-[13px] text-[#475467]">
          <p>conversation.intent: proposal_generation</p>
          <p>conversation.prospect: Axon Group</p>
          <p>tool.last_result: CRM opportunity score 0.82</p>
        </div>
      ) : null}
    </div>
  );
}

