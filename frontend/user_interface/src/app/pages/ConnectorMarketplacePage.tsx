import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { listConnectorCatalog, type ConnectorCatalogRecord } from "../../api/client";

type Category =
  | "all"
  | "crm"
  | "research"
  | "finance"
  | "productivity"
  | "database"
  | "communication"
  | "other";

function normalizeCategory(value: string): Category {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "crm") {
    return "crm";
  }
  if (
    normalized === "research" ||
    normalized === "search" ||
    normalized === "news" ||
    normalized === "sentiment"
  ) {
    return "research";
  }
  if (normalized === "finance" || normalized === "fintech" || normalized === "sec") {
    return "finance";
  }
  if (normalized === "communication") {
    return "communication";
  }
  if (normalized === "data" || normalized === "analytics") {
    return "database";
  }
  if (normalized === "developer_tools" || normalized === "calendar" || normalized === "storage") {
    return "productivity";
  }
  return "other";
}

function toDisplayCategory(value: Category) {
  if (value === "productivity") {
    return "productivity";
  }
  if (value === "database") {
    return "database";
  }
  if (value === "communication") {
    return "communication";
  }
  if (value === "research") {
    return "research";
  }
  if (value === "finance") {
    return "finance";
  }
  if (value === "crm") {
    return "crm";
  }
  return "other";
}

function navigateToPath(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function ConnectorMarketplacePage() {
  const [category, setCategory] = useState<Category>("all");
  const [rows, setRows] = useState<ConnectorCatalogRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const connectors = await listConnectorCatalog();
        setRows(connectors || []);
      } catch (nextError) {
        setError(String(nextError || "Failed to load connector catalog."));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const filteredRows = useMemo(() => {
    if (category === "all") {
      return rows;
    }
    return rows.filter((item) => normalizeCategory(item.category || "other") === category);
  }, [category, rows]);

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1220px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">
            Connector marketplace
          </p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">
            Discover connectors
          </h1>
          <div className="mt-4 flex flex-wrap gap-2">
            {(
              [
                "all",
                "crm",
                "research",
                "finance",
                "productivity",
                "database",
                "communication",
                "other",
              ] as const
            ).map(
              (value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setCategory(value)}
                  className={`rounded-full px-3 py-1.5 text-[12px] font-semibold capitalize ${
                    category === value
                      ? "bg-[#111827] text-white"
                      : "border border-black/[0.12] bg-white text-[#344054]"
                  }`}
                >
                  {value}
                </button>
              ),
            )}
          </div>
        </section>

        {error ? (
          <section className="rounded-2xl border border-[#fca5a5] bg-[#fff1f2] p-4 text-[13px] text-[#9f1239]">
            {error}
          </section>
        ) : null}

        {loading ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-6 text-[14px] text-[#667085]">
            Loading connector catalog...
          </section>
        ) : (
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filteredRows.map((row) => (
              <article key={row.id} className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <p className="text-[12px] text-[#667085]">{row.author || "Maia Connector"}</p>
                <h2 className="mt-1 text-[18px] font-semibold text-[#111827]">{row.name}</h2>
                <p className="mt-2 text-[13px] text-[#475467]">{row.description || "No description provided."}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
                    {toDisplayCategory(normalizeCategory(row.category || "other"))}
                  </span>
                  <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
                    {(row.tools || []).length} tools
                  </span>
                  <span className="rounded-full border border-[#d0d5dd] bg-white px-2.5 py-1 text-[11px] font-semibold uppercase text-[#344054]">
                    {String(row.auth?.kind || "none")}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    toast.success(`${row.name} is available. Configure credentials in Connectors.`);
                    navigateToPath("/connectors");
                  }}
                  className="mt-4 rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white"
                >
                  Configure connector
                </button>
              </article>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
