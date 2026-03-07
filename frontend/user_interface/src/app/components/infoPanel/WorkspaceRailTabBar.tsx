import { WORKSPACE_RAIL_TABS, type WorkspaceRailTab } from "./workspaceRailTabs";
import type { WorkspaceRenderMode } from "./workspaceRenderModes";

type WorkspaceRailTabBarProps = {
  activeTab: WorkspaceRailTab;
  onChangeTab: (tab: WorkspaceRailTab) => void;
  workspaceRenderMode: WorkspaceRenderMode;
  onChangeRenderMode: (mode: WorkspaceRenderMode) => void;
};

const RENDER_MODES: WorkspaceRenderMode[] = ["fast", "balanced", "full"];

function WorkspaceRailTabBar({
  activeTab,
  onChangeTab,
  workspaceRenderMode,
  onChangeRenderMode,
}: WorkspaceRailTabBarProps) {
  return (
    <div className="border-b border-black/[0.06] px-5 py-2.5">
      <div className="flex items-center gap-1 overflow-x-auto pb-0.5">
        {WORKSPACE_RAIL_TABS.map((row) => {
          const active = row.id === activeTab;
          return (
            <button
              key={row.id}
              type="button"
              onClick={() => onChangeTab(row.id)}
              className={`shrink-0 rounded-full border px-3 py-1.5 text-[11px] tracking-wide transition ${
                active
                  ? "border-[#1d1d1f] bg-[#1d1d1f] text-white"
                  : "border-black/[0.08] bg-white text-[#4c4c50] hover:bg-[#f3f3f5]"
              }`}
            >
              {row.label}
            </button>
          );
        })}
      </div>
      <div className="mt-2 inline-flex items-center gap-1 rounded-full border border-black/[0.08] bg-white p-1">
        {RENDER_MODES.map((mode) => {
          const active = mode === workspaceRenderMode;
          return (
            <button
              key={mode}
              type="button"
              onClick={() => onChangeRenderMode(mode)}
              className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide transition ${
                active
                  ? "bg-[#1d1d1f] text-white"
                  : "text-[#4c4c50] hover:bg-[#f3f3f5]"
              }`}
            >
              {mode}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export { WorkspaceRailTabBar };
