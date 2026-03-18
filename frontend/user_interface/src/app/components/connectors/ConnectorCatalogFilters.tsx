import {
  SUITE_DEFINITIONS,
  suiteAccentClass,
  suiteFilterLabel,
} from "./catalogModel";
import type {
  ConnectorListFilter,
  ConnectorSuiteFilter,
  ConnectorSuiteKey,
} from "./catalogModel";

type ConnectorCatalogFiltersProps = {
  activeFilter: ConnectorListFilter;
  activeSuite: ConnectorSuiteFilter;
  filteredCount: number;
  suiteCounts: Record<ConnectorSuiteKey, number>;
  onFilterChange: (value: ConnectorListFilter) => void;
  onSuiteChange: (value: ConnectorSuiteFilter) => void;
};

export function ConnectorCatalogFilters({
  activeFilter,
  activeSuite,
  filteredCount,
  suiteCounts,
  onFilterChange,
  onSuiteChange,
}: ConnectorCatalogFiltersProps) {
  return (
    <section className="rounded-[20px] border border-black/[0.06] bg-white px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-[#86868b]">
          Status
        </span>
        {(
          [
            ["needs_setup", "Needs setup"],
            ["connected", "Connected"],
            ["attention", "Attention"],
            ["all", "All"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => onFilterChange(value)}
            className={`rounded-full px-3 py-1.5 text-[12px] font-medium transition-all ${
              activeFilter === value
                ? "bg-[#7c3aed] text-white shadow-[0_1px_3px_rgba(124,58,237,0.3)]"
                : "border border-black/[0.06] bg-white text-[#3a3a40] hover:bg-[#f5f3ff] hover:text-[#7c3aed]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-black/[0.04] pt-3">
        <span className="mr-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-[#86868b]">
          Suite
        </span>
        {(["all", ...SUITE_DEFINITIONS.map((suite) => suite.key)] as const).map(
          (value) => {
            const count =
              value === "all"
                ? filteredCount
                : suiteCounts[value as ConnectorSuiteKey];
            const isActive = activeSuite === value;
            return (
              <button
                key={value}
                type="button"
                onClick={() => onSuiteChange(value)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium transition-all ${
                  isActive
                    ? "bg-[#7c3aed] text-white shadow-[0_1px_3px_rgba(124,58,237,0.3)]"
                    : "border border-black/[0.06] bg-white text-[#3a3a40] hover:bg-[#f5f3ff] hover:text-[#7c3aed]"
                }`}
              >
                {value !== "all" ? (
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      isActive ? "bg-white/60" : suiteAccentClass(value as ConnectorSuiteKey)
                    }`}
                  />
                ) : null}
                <span>{suiteFilterLabel(value)}</span>
                <span
                  className={`ml-0.5 text-[10px] tabular-nums ${
                    isActive ? "text-white/70" : "text-[#86868b]"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          },
        )}
      </div>
    </section>
  );
}
