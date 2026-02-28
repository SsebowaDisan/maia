import type { AgentActivityEvent } from "../../types";
import type { PreviewTab } from "../agentActivityMeta";

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
  return (
    <div className="mb-3 rounded-2xl border border-black/[0.06] bg-white/90 p-3">
      <div className="mb-2 inline-flex rounded-xl border border-black/[0.08] bg-[#f5f5f7] p-1">
        {[
          { id: "browser", label: "Browser", count: browserEvents.length },
          { id: "document", label: "Document", count: documentEvents.length },
          { id: "email", label: "Email", count: emailEvents.length },
          { id: "system", label: "System", count: systemEvents.length },
        ].map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setPreviewTab(item.id as PreviewTab)}
            className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition ${
              previewTab === item.id ? "bg-[#1d1d1f] text-white" : "text-[#4c4c50] hover:bg-white"
            }`}
          >
            {item.label} ({item.count})
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-black/[0.06] bg-[#fafafc] p-2.5">
        {previewTab === "browser" ? (
          <div className="space-y-1">
            <p className="text-[12px] font-medium text-[#1d1d1f]">Live browser actions</p>
            {browserEvents.length > 0 ? (
              <div className="max-h-32 space-y-1 overflow-y-auto pr-1">
                {browserEvents.map((event) => (
                  <p key={`browser-${event.event_id}`} className="text-[11px] text-[#4c4c50]">
                    {event.title}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-[#6e6e73]">No browser actions in this run yet.</p>
            )}
          </div>
        ) : null}
        {previewTab === "document" ? (
          <div className="space-y-1">
            <p className="text-[12px] font-medium text-[#1d1d1f]">Live document actions</p>
            <p className="text-[11px] text-[#4c4c50]">Current source: {stageFileName}</p>
            {documentEvents.length > 0 ? (
              <div className="max-h-32 space-y-1 overflow-y-auto pr-1">
                {documentEvents.map((event) => (
                  <p key={`doc-${event.event_id}`} className="text-[11px] text-[#4c4c50]">
                    {event.title}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-[#6e6e73]">No document actions in this run yet.</p>
            )}
          </div>
        ) : null}
        {previewTab === "email" ? (
          <div className="space-y-1">
            <p className="text-[12px] font-medium text-[#1d1d1f]">Live email actions</p>
            {emailEvents.length > 0 ? (
              <div className="max-h-32 space-y-1 overflow-y-auto pr-1">
                {emailEvents.map((event) => (
                  <p key={`email-${event.event_id}`} className="text-[11px] text-[#4c4c50]">
                    {event.title}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-[#6e6e73]">No email actions in this run yet.</p>
            )}
          </div>
        ) : null}
        {previewTab === "system" ? (
          <div className="space-y-1">
            <p className="text-[12px] font-medium text-[#1d1d1f]">System session view</p>
            <p className="text-[11px] text-[#4c4c50]">
              Active focus: {activeTab} | Total events: {totalEvents}
            </p>
            {systemEvents.length > 0 ? (
              <div className="max-h-32 space-y-1 overflow-y-auto pr-1">
                {systemEvents.map((event) => (
                  <p key={`system-${event.event_id}`} className="text-[11px] text-[#4c4c50]">
                    {event.title}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-[#6e6e73]">No system events in this run yet.</p>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export { PreviewTabsCard };
