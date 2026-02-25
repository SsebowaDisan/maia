import { ChevronLeft } from "lucide-react";

interface TopNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const workspaceTabs = ["Files", "Resources", "Settings", "Help"];

export function TopNav({ activeTab, onTabChange }: TopNavProps) {
  const isChatPage = activeTab === "Chat";

  return (
    <div className="relative flex items-center justify-center h-12 bg-white border-b border-[#ececef] px-4">
      <div className="absolute left-4">
        {isChatPage ? (
          <span className="text-[12px] text-[#8d8d93]">Chat</span>
        ) : (
          <button
            onClick={() => onTabChange("Chat")}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] text-[#1d1d1f] hover:bg-[#f5f5f7] transition-colors"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            <span>Back to Chat</span>
          </button>
        )}
      </div>

      <div className="flex items-center gap-6">
        {isChatPage ? (
          <h1 className="text-[14px] font-medium tracking-tight text-[#1d1d1f]">
            Maia
          </h1>
        ) : (
          <div className="flex items-center gap-6">
            {workspaceTabs.map((tab) => (
              <button
                key={tab}
                onClick={() => onTabChange(tab)}
                className={`relative pb-1 text-[13px] transition-colors ${
                  activeTab === tab
                    ? "text-[#1d1d1f] font-semibold"
                    : "text-[#86868b] hover:text-[#1d1d1f]"
                }`}
              >
                {tab}
                {activeTab === tab ? (
                  <span className="absolute left-0 right-0 -bottom-[1px] h-[2px] rounded-full bg-[#1d1d1f]" />
                ) : null}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="absolute right-6 text-[11px] text-[#1d1d1f]/50">
        v0.01
      </div>
    </div>
  );
}
