import type { TableColumn, TableRow } from "./types";

type ResourceTableProps = {
  columns: TableColumn[];
  rows: TableRow[];
};

function ResourceTable({ columns, rows }: ResourceTableProps) {
  return (
    <div className="border border-[#e5e5e5] rounded-lg overflow-hidden">
      <table className="w-full">
        <thead className="bg-[#fafafa] border-b border-[#e5e5e5]">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal"
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`row-${rowIndex}`} className="border-b border-[#e5e5e5] last:border-b-0">
              {columns.map((column) => (
                <td key={`${rowIndex}-${column.key}`} className="px-4 py-4 text-[13px] text-[#1d1d1f]">
                  {String(row[column.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export { ResourceTable };
