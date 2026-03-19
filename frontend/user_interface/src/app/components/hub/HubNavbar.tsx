import { Menu, Search } from "lucide-react";
import { useMemo, useState } from "react";

type HubNavbarProps = {
  currentPath: string;
  onNavigate: (path: string) => void;
};

type NavItem = {
  id: string;
  label: string;
  path: string;
  matches: (path: string) => boolean;
};

const NAV_ITEMS: NavItem[] = [
  {
    id: "explore",
    label: "Explore",
    path: "/explore",
    matches: (path) => path.startsWith("/explore"),
  },
  {
    id: "agents",
    label: "Agents",
    path: "/marketplace",
    matches: (path) => path === "/marketplace" || path.startsWith("/marketplace/agents/"),
  },
  {
    id: "teams",
    label: "Teams",
    path: "/marketplace/teams",
    matches: (path) => path.startsWith("/marketplace/teams"),
  },
  {
    id: "feed",
    label: "Feed",
    path: "/feed",
    matches: (path) => path.startsWith("/feed"),
  },
];

function readSearchQueryFromUrl(): string {
  const params = new URLSearchParams(window.location.search || "");
  return String(params.get("q") || "").trim();
}

export function HubNavbar({ currentPath, onNavigate }: HubNavbarProps) {
  const [searchDraft, setSearchDraft] = useState(() => readSearchQueryFromUrl());
  const [mobileOpen, setMobileOpen] = useState(false);

  const normalizedPath = String(currentPath || "/").toLowerCase();
  const activeItemId = useMemo(() => {
    const match = NAV_ITEMS.find((item) => item.matches(normalizedPath));
    return match?.id || "";
  }, [normalizedPath]);

  const runSearch = () => {
    const query = searchDraft.trim();
    if (!query) {
      onNavigate("/explore");
      return;
    }
    onNavigate(`/explore?q=${encodeURIComponent(query)}`);
  };

  return (
    <header className="sticky top-0 z-40 border-b border-black/[0.08] bg-white/95 backdrop-blur-xl">
      <div className="mx-auto flex h-[72px] w-full max-w-[1240px] items-center gap-3 px-4 sm:px-6">
        <button
          type="button"
          className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-black/[0.08] text-[#3b3b41] md:hidden"
          onClick={() => setMobileOpen((previous) => !previous)}
          aria-label="Toggle navigation menu"
        >
          <Menu className="h-4 w-4" />
        </button>

        <button
          type="button"
          onClick={() => onNavigate("/marketplace")}
          className="shrink-0 text-left"
        >
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#707785]">Micrurus Hub</p>
          <p className="text-[17px] font-semibold tracking-[-0.02em] text-[#0f172a]">Marketplace</p>
        </button>

        <nav
          className={`${mobileOpen ? "flex" : "hidden"} absolute left-4 right-4 top-[78px] flex-col gap-1 rounded-2xl border border-black/[0.08] bg-white p-2 shadow-[0_14px_34px_rgba(15,23,42,0.1)] md:static md:flex md:flex-row md:border-0 md:bg-transparent md:p-0 md:shadow-none`}
        >
          {NAV_ITEMS.map((item) => {
            const active = item.id === activeItemId;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setMobileOpen(false);
                  onNavigate(item.path);
                }}
                className={`rounded-xl px-3 py-2 text-[13px] font-medium transition-colors ${
                  active ? "bg-[#111827] text-white" : "text-[#39404f] hover:bg-[#eef2ff]"
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="ml-auto hidden max-w-[380px] flex-1 items-center gap-2 rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 md:flex">
          <Search className="h-4 w-4 text-[#6b7280]" />
          <input
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                runSearch();
              }
            }}
            placeholder="Search agents, teams, creators..."
            className="w-full bg-transparent text-[13px] text-[#111827] placeholder:text-[#9ca3af] outline-none"
          />
        </div>

        <a
          href="/"
          className="shrink-0 rounded-xl border border-black/[0.08] bg-white px-3 py-2 text-[12px] font-semibold text-[#111827] transition hover:bg-[#f8fafc]"
        >
          Back to Chat
        </a>
      </div>
    </header>
  );
}
