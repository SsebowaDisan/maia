import type { ReactNode } from "react";

import { SettingsSidebar } from "./SettingsSidebar";
import type { SettingsTabId, SettingsTabItem } from "../types";

type SettingsLayoutProps = {
  title: string;
  subtitle: string;
  tabs: SettingsTabItem[];
  activeTab: SettingsTabId;
  onChangeTab: (tab: SettingsTabId) => void;
  headerAction?: ReactNode;
  children: ReactNode;
};

export function SettingsLayout({
  title,
  subtitle,
  tabs,
  activeTab,
  onChangeTab,
  headerAction,
  children,
}: SettingsLayoutProps) {
  return (
    <div className="flex-1 overflow-hidden bg-white">
      <div className="mx-auto h-full max-w-[1420px] px-4 pb-8 pt-6 sm:px-6 lg:px-8">
        <div className="flex h-full min-h-0 gap-8">
          <div className="hidden w-[260px] shrink-0 md:block">
            <SettingsSidebar items={tabs} activeTab={activeTab} onChangeTab={onChangeTab} />
          </div>

          <main className="min-h-0 min-w-0 flex-1 overflow-y-auto pr-1">
            <div className="mx-auto max-w-[1060px]">
              <header className="flex flex-wrap items-start justify-between gap-4 pb-6">
                <div>
                  <h1 className="text-[30px] font-semibold leading-tight text-[#1d1d1f]">{title}</h1>
                  <p className="mt-1 text-[14px] text-[#6e6e73]">{subtitle}</p>
                </div>
                {headerAction ? <div className="pt-1">{headerAction}</div> : null}
              </header>

              <div className="mb-6 md:hidden">
                <nav className="flex flex-wrap gap-2">
                  {tabs.map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => onChangeTab(tab.id)}
                      aria-current={activeTab === tab.id ? "page" : undefined}
                      className={`rounded-full px-4 py-2 text-[12px] font-semibold transition ${
                        activeTab === tab.id
                          ? "bg-[#1d1d1f] text-white"
                          : "border border-[#d2d2d7] bg-white text-[#525259] hover:bg-[#f5f5f7]"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </nav>
              </div>

              <div className="space-y-8">{children}</div>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
