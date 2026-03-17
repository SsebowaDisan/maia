import { useMemo, useState } from "react";
import { ArrowDownUp, ArrowUp, ArrowDown, Search } from "lucide-react";

type SortDirection = "asc" | "desc";

type SortableTableWidgetProps = {
  title?: string;
  columns?: string[];
  rows?: Array<Record<string, unknown> | unknown[]>;
};

type NormalizedRow = {
  values: string[];
  searchText: string;
};

function normalizeColumns(columns: unknown): string[] {
  if (!Array.isArray(columns)) {
    return [];
  }
  return columns
    .map((entry) => String(entry || "").trim())
    .filter(Boolean);
}

function normalizeRows(
  rows: Array<Record<string, unknown> | unknown[]>,
  columns: string[],
): NormalizedRow[] {
  const normalized: NormalizedRow[] = [];
  for (const row of rows) {
    if (Array.isArray(row)) {
      const values = row.map((entry) => String(entry ?? "").trim());
      normalized.push({
        values,
        searchText: values.join(" ").toLowerCase(),
      });
      continue;
    }
    if (row && typeof row === "object") {
      const record = row as Record<string, unknown>;
      const values =
        columns.length > 0
          ? columns.map((column) => String(record[column] ?? "").trim())
          : Object.values(record).map((entry) => String(entry ?? "").trim());
      normalized.push({
        values,
        searchText: values.join(" ").toLowerCase(),
      });
    }
  }
  return normalized;
}

function SortableTableWidget({ title, columns = [], rows = [] }: SortableTableWidgetProps) {
  const parsedColumns = useMemo(() => normalizeColumns(columns), [columns]);
  const parsedRows = useMemo(() => normalizeRows(Array.isArray(rows) ? rows : [], parsedColumns), [rows, parsedColumns]);
  const effectiveColumns = useMemo(() => {
    if (parsedColumns.length > 0) {
      return parsedColumns;
    }
    const maxCols = parsedRows.reduce((max, row) => Math.max(max, row.values.length), 0);
    return Array.from({ length: maxCols }, (_, index) => `Column ${index + 1}`);
  }, [parsedColumns, parsedRows]);

  const [search, setSearch] = useState("");
  const [sortIndex, setSortIndex] = useState(0);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    const base = query ? parsedRows.filter((row) => row.searchText.includes(query)) : parsedRows.slice();
    base.sort((left, right) => {
      const a = String(left.values[sortIndex] ?? "");
      const b = String(right.values[sortIndex] ?? "");
      const comparison = a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
      return sortDirection === "asc" ? comparison : -comparison;
    });
    return base;
  }, [parsedRows, search, sortDirection, sortIndex]);

  const onSort = (index: number) => {
    if (index === sortIndex) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortIndex(index);
    setSortDirection("asc");
  };

  return (
    <section className="overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-[0_16px_32px_rgba(15,23,42,0.05)]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-black/[0.06] px-4 py-3">
        <p className="text-[14px] font-semibold text-[#101828]">{title || "Data table"}</p>
        <label className="relative w-full max-w-[260px]">
          <Search
            size={13}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#98a2b3]"
          />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Filter rows"
            className="w-full rounded-full border border-black/[0.12] bg-white py-1.5 pl-8 pr-3 text-[12px] text-[#111827] outline-none focus:border-black/[0.22]"
          />
        </label>
      </div>

      <div className="max-h-[340px] overflow-auto">
        <table className="min-w-full border-collapse text-left text-[12px] text-[#344054]">
          <thead className="sticky top-0 z-10 bg-[#f8fafc]">
            <tr>
              {effectiveColumns.map((column, index) => (
                <th key={`${column}-${index}`} className="border-b border-black/[0.06] px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() => onSort(index)}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#667085]"
                  >
                    {column}
                    {sortIndex !== index ? <ArrowDownUp size={12} /> : null}
                    {sortIndex === index && sortDirection === "asc" ? <ArrowUp size={12} /> : null}
                    {sortIndex === index && sortDirection === "desc" ? <ArrowDown size={12} /> : null}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredRows.length === 0 ? (
              <tr>
                <td
                  colSpan={Math.max(1, effectiveColumns.length)}
                  className="px-3 py-6 text-center text-[12px] text-[#667085]"
                >
                  No rows match the current filter.
                </td>
              </tr>
            ) : null}
            {filteredRows.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`} className="border-b border-black/[0.04] last:border-b-0">
                {effectiveColumns.map((_, columnIndex) => (
                  <td key={`cell-${rowIndex}-${columnIndex}`} className="px-3 py-2.5 align-top">
                    {String(row.values[columnIndex] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export { SortableTableWidget };
export type { SortableTableWidgetProps };
