import type { AgentActivityEvent } from "../../types";
import type { PreviewTab } from "../agentActivityMeta";
import { styleForEvent } from "../agentActivityMeta";

interface PreviewTabsCardProps {
  previewTab: PreviewTab;
  setPreviewTab: (tab: PreviewTab) => void;
  browserEvents: AgentActivityEvent[];
  documentEvents: AgentActivityEvent[];
  emailEvents: AgentActivityEvent[];
  systemEvents: AgentActivityEvent[];
  stageFileName: string;
  activeTab: string;
  totalEvents: number;
}

function PreviewTabsCard({
  previewTab,
  setPreviewTab,
  browserEvents,
  documentEvents,
  emailEvents,
  systemEvents,
  stageFileName,
  activeTab,
  totalEvents,
}: PreviewTabsCardProps) {
  const tabRows: Array<{ id: PreviewTab; label: string; events: AgentActivityEvent[] }> = [
    { id: "browser", label: "Browser", events: browserEvents },
    { id: "document", label: "Document", events: documentEvents },
    { id: "email", label: "Email", events: emailEvents },
    { id: "system", label: "System", events: systemEvents },
  ];
  const activeRow = tabRows.find((row) => row.id === previewTab) || tabRows[0];
  const activeEvents = activeRow.events;

  const renderEventRows = (events: AgentActivityEvent[]) => {
    if (!events.length) {
      return (
        <p className="text-[11px] text-[#6e6e73]">No events yet in this surface.</p>
      );
    }
    return (
      <div className="max-h-32 space-y-1 overflow-y-auto pr-1">
        {events.map((event) => {
          const style = styleForEvent(event.event_type || "");
          const headline = String(event.title || "").trim() || style.label;
          const detail = String(event.detail || "").trim();
          return (
            <p key={`${activeRow.id}-${event.event_id}`} className="text-[11px] text-[#4c4c50]">
              <span className="font-medium text-[#1d1d1f]">{style.label}</span>
              <span>{` · ${headline}`}</span>
              {detail && detail !== headline ? <span className="text-[#6e6e73]">{` — ${detail}`}</span> : null}
            </p>
          );
        })}
      </div>
    );
  };

  return (
    <div className="mb-3 rounded-2xl border border-black/[0.06] bg-white/90 p-3">
      <div className="mb-2 inline-flex rounded-xl border border-black/[0.08] bg-[#f5f5f7] p-1">
        {tabRows.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setPreviewTab(item.id as PreviewTab)}
            className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition ${
              previewTab === item.id ? "bg-[#1d1d1f] text-white" : "text-[#4c4c50] hover:bg-white"
            }`}
          >
            {item.label} ({item.events.length})
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-black/[0.06] bg-[#fafafc] p-2.5">
        <div className="space-y-1">
          <p className="text-[12px] font-medium text-[#1d1d1f]">{`${activeRow.label} events`}</p>
          {previewTab === "document" ? (
            <p className="text-[11px] text-[#4c4c50]">Current source: {stageFileName}</p>
          ) : null}
          {previewTab === "system" ? (
            <p className="text-[11px] text-[#4c4c50]">
              Active focus: {activeTab} | Total events: {totalEvents}
            </p>
          ) : null}
          {renderEventRows(activeEvents)}
        </div>
      </div>
    </div>
  );
}

export { PreviewTabsCard };
