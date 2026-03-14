import { useMemo, useState } from "react";
import { toast } from "sonner";

import { AGENT_OS_CONNECTORS } from "./agentOsData";

type Category = "all" | "crm" | "productivity" | "database" | "communication";

const CONNECTOR_MARKETPLACE = [
  {
    id: "salesforce",
    name: "Salesforce",
    publisher: "Maia Verified",
    category: "crm" as const,
    toolsCount: 8,
    installs: 2200,
    description: "Complete CRM records and pipeline operations.",
  },
  {
    id: "jira",
    name: "Jira",
    publisher: "Atlassian Labs",
    category: "productivity" as const,
    toolsCount: 6,
    installs: 1240,
    description: "Issue lifecycle and sprint automation.",
  },
  {
    id: "postgres_query",
    name: "Postgres Query",
    publisher: "Maia Core",
    category: "database" as const,
    toolsCount: 4,
    installs: 1680,
    description: "Read-only SQL analytics and schema introspection.",
  },
  {
    id: "slack",
    name: "Slack",
    publisher: "Maia Verified",
    category: "communication" as const,
    toolsCount: 5,
    installs: 3010,
    description: "Channel messaging, monitoring, and notifications.",
  },
];

export function ConnectorMarketplacePage() {
  const [category, setCategory] = useState<Category>("all");
  const [installedIds, setInstalledIds] = useState<string[]>(
    AGENT_OS_CONNECTORS.map((connector) => connector.id),
  );

  const rows = useMemo(
    () =>
      CONNECTOR_MARKETPLACE.filter((item) => category === "all" || item.category === category),
    [category],
  );

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1220px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Connector marketplace</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Discover connectors</h1>
          <div className="mt-4 flex flex-wrap gap-2">
            {(["all", "crm", "productivity", "database", "communication"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setCategory(value)}
                className={`rounded-full px-3 py-1.5 text-[12px] font-semibold capitalize ${
                  category === value ? "bg-[#111827] text-white" : "border border-black/[0.12] bg-white text-[#344054]"
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {rows.map((row) => {
            const installed = installedIds.includes(row.id);
            return (
              <article key={row.id} className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <p className="text-[12px] text-[#667085]">{row.publisher}</p>
                <h2 className="mt-1 text-[18px] font-semibold text-[#111827]">{row.name}</h2>
                <p className="mt-2 text-[13px] text-[#475467]">{row.description}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
                    {row.category}
                  </span>
                  <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
                    {row.toolsCount} tools
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setInstalledIds((previous) => (previous.includes(row.id) ? previous : [...previous, row.id]));
                    toast.success(`${row.name} installed and available in builder.`);
                  }}
                  className={`mt-4 rounded-full px-4 py-2 text-[12px] font-semibold ${
                    installed
                      ? "border border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]"
                      : "bg-[#111827] text-white"
                  }`}
                >
                  {installed ? "Installed" : "Install"}
                </button>
              </article>
            );
          })}
        </section>
      </div>
    </div>
  );
}

