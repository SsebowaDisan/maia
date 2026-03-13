import { FileText, HelpCircle, Library, Settings, X } from "lucide-react";
import type { ReactNode } from "react";

type WorkspaceOverlayTab = "Files" | "Resources" | "Settings" | "Help";

type WorkspaceOverlayModalProps = {
  tab: WorkspaceOverlayTab;
  onClose: () => void;
  children: ReactNode;
};

const TAB_CONFIG: Record<
  WorkspaceOverlayTab,
  {
    icon: typeof FileText;
    subtitle: string;
  }
> = {
  Files: {
    icon: FileText,
    subtitle: "Everything you upload, organized in one focused workspace.",
  },
  Resources: {
    icon: Library,
    subtitle: "Model and connector inventory, designed for clean operations.",
  },
  Settings: {
    icon: Settings,
    subtitle: "Control the system behavior with deliberate precision.",
  },
  Help: {
    icon: HelpCircle,
    subtitle: "Clear guidance, no noise.",
  },
};

export function WorkspaceOverlayModal({ tab, onClose, children }: WorkspaceOverlayModalProps) {
  const config = TAB_CONFIG[tab];
  const TabIcon = config.icon;
  const contentViewportClassName =
    tab === "Files"
      ? "flex h-full min-h-0 overflow-hidden"
      : "h-full min-h-0 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]";

  return (
    <div
      className="fixed inset-0 z-[170] flex items-center justify-center p-4 sm:p-6 md:p-10"
      role="dialog"
      aria-modal="true"
      aria-label={`${tab} panel`}
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_6%,rgba(255,255,255,0.36)_0%,rgba(241,241,244,0.7)_36%,rgba(27,27,31,0.4)_100%)] backdrop-blur-[10px]" />
      <div
        className="relative z-[171] flex h-[min(90vh,980px)] w-full max-w-[1320px] min-h-[560px] flex-col overflow-hidden rounded-[30px] border border-white/70 bg-[linear-gradient(155deg,#fcfcfd_0%,#f6f6f8_44%,#ececef_100%)] shadow-[0_46px_124px_-48px_rgba(0,0,0,0.62)]"
        style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif" }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-black/[0.08] px-6 py-4">
          <div className="flex items-center gap-4">
            <div className="inline-flex items-center gap-2.5 rounded-full border border-black/[0.08] bg-white/80 px-3 py-1">
              <TabIcon className="h-3.5 w-3.5 text-[#5f5f65]" />
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#4f4f55]">
                {tab}
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.08] text-[#6e6e73] transition-colors hover:bg-white hover:text-[#1d1d1f]"
            aria-label={`Close ${tab}`}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-6 pb-4 pt-5">
          <p className="text-[24px] font-semibold tracking-[-0.015em] text-[#141417]">{tab}</p>
          <p className="mt-1 text-[13px] text-[#5f5f65]">{config.subtitle}</p>
        </div>

        <div className="min-h-0 flex-1 border-t border-white/70 bg-white/76 px-2 pb-2">
          <div className="h-full rounded-2xl border border-black/[0.06] bg-white/90">
            <div className={contentViewportClassName}>{children}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export type { WorkspaceOverlayTab };
