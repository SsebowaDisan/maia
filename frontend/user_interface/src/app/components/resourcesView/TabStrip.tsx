type TabStripProps<T extends string> = {
  tabs: Array<{ id: T; label: string }>;
  activeTab: T;
  onChange: (tab: T) => void;
  className?: string;
};

function TabStrip<T extends string>({
  tabs,
  activeTab,
  onChange,
  className = "",
}: TabStripProps<T>) {
  return (
    <div className={`flex items-center gap-6 border-b border-[#e5e5e5] ${className}`}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`pb-2 text-[13px] transition-all border-b-2 ${
            activeTab === tab.id
              ? "text-[#1d1d1f] border-[#1d1d1f]"
              : "text-[#86868b] border-transparent hover:text-[#1d1d1f]"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export { TabStrip };
