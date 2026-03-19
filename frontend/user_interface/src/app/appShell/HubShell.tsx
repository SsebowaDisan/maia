import type { ReactNode } from "react";

import { HubNavbar } from "../components/hub/HubNavbar";

type HubShellProps = {
  currentPath: string;
  onNavigate: (path: string) => void;
  children: ReactNode;
};

export function HubShell({ currentPath, onNavigate, children }: HubShellProps) {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#f8fbff_0%,#f4f6fb_40%,#eef1f7_100%)] text-[#0f172a]">
      <HubNavbar currentPath={currentPath} onNavigate={onNavigate} />
      <main className="mx-auto w-full max-w-[1240px] px-4 pb-12 pt-6 sm:px-6">{children}</main>
      <footer className="border-t border-black/[0.08] bg-white/85">
        <div className="mx-auto flex w-full max-w-[1240px] items-center justify-between px-4 py-4 text-[12px] text-[#667085] sm:px-6">
          <span>Micrurus Hub</span>
          <span>Build, share, and run AI agents and teams.</span>
        </div>
      </footer>
    </div>
  );
}
