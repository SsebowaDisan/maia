import type { SettingsTabId, SettingsTabItem } from "../types";

type SettingsSidebarProps = {
  items: SettingsTabItem[];
  activeTab: SettingsTabId;
  onChangeTab: (tab: SettingsTabId) => void;
};

function ItemButton({
  item,
  active,
  onClick,
}: {
  item: SettingsTabItem;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`w-full rounded-xl px-3 py-2 text-left transition ${
        active ? "bg-[#f1f1f4] text-[#1d1d1f]" : "text-[#525259] hover:bg-[#f7f7f8] hover:text-[#1d1d1f]"
      }`}
    >
      <p className="text-[13px] font-semibold">{item.label}</p>
      <p className="mt-0.5 text-[11px] text-[#8e8e93]">{item.subtitle}</p>
    </button>
  );
}

export function SettingsSidebar({ items, activeTab, onChangeTab }: SettingsSidebarProps) {
  return (
    <aside className="sticky top-6">
      <p className="px-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[#8e8e93]">Settings</p>
      <nav className="mt-3 space-y-1">
        {items.map((item) => (
          <ItemButton
            key={item.id}
            item={item}
            active={activeTab === item.id}
            onClick={() => onChangeTab(item.id)}
          />
        ))}
      </nav>
    </aside>
  );
}
