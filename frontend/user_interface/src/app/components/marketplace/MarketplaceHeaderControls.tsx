import { Search } from "lucide-react";

type MarketplacePricingFilter = "all" | "free" | "paid" | "enterprise";

type MarketplaceHeaderControlsProps = {
  query: string;
  onQueryChange: (value: string) => void;
  pricingFilter: MarketplacePricingFilter;
  onPricingFilterChange: (value: MarketplacePricingFilter) => void;
  resultCount: number;
  compact?: boolean;
};

export function MarketplaceHeaderControls({
  query,
  onQueryChange,
  pricingFilter,
  onPricingFilterChange,
  resultCount,
  compact = false,
}: MarketplaceHeaderControlsProps) {
  return (
    <div
      className={`flex flex-wrap items-center gap-2 ${
        compact ? "" : "rounded-[18px] border border-black/[0.08] bg-white/80 px-3 py-2"
      }`}
    >
      <label className="relative min-w-[280px]">
        <Search
          className={`pointer-events-none absolute left-3 text-[#98a2b3] ${
            compact ? "top-2" : "top-2.5"
          }`}
          size={compact ? 14 : 15}
        />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search by name or description"
          className={`w-full rounded-full border border-black/[0.12] bg-white pl-9 pr-3 ${
            compact ? "py-1.5 text-[12px]" : "py-2 text-[13px]"
          }`}
        />
      </label>
      {(["all", "free", "paid", "enterprise"] as const).map((value) => (
        <button
          key={value}
          type="button"
          onClick={() => onPricingFilterChange(value)}
          className={`rounded-full font-semibold capitalize transition-colors ${
            compact ? "px-2.5 py-1 text-[11px]" : "px-3 py-1.5 text-[12px]"
          } ${
            pricingFilter === value
              ? "bg-[#7c3aed] text-white shadow-[0_1px_3px_rgba(124,58,237,0.3)]"
              : "border border-black/[0.12] bg-white text-[#344054]"
          }`}
        >
          {value}
        </button>
      ))}
      <span
        className={`ml-auto rounded-full border border-black/[0.1] bg-[#f8fafc] font-semibold text-[#475467] ${
          compact ? "px-2.5 py-1 text-[10px]" : "px-3 py-1 text-[11px]"
        }`}
      >
        {resultCount} results
      </span>
    </div>
  );
}

export type { MarketplacePricingFilter, MarketplaceHeaderControlsProps };
