type MultiAgentColumn = {
  agentId: string;
  agentName: string;
  status: "pending" | "running" | "done" | "blocked";
  events: string[];
};

type MultiAgentTheatreProps = {
  columns: MultiAgentColumn[];
};

function badgeClass(status: MultiAgentColumn["status"]): string {
  if (status === "done") {
    return "bg-[#ecfdf3] text-[#166534]";
  }
  if (status === "running") {
    return "bg-[#eff6ff] text-[#1d4ed8]";
  }
  if (status === "blocked") {
    return "bg-[#fff7ed] text-[#9a3412]";
  }
  return "bg-[#f2f4f7] text-[#475467]";
}

export function MultiAgentTheatre({ columns }: MultiAgentTheatreProps) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="flex min-w-max gap-3">
        {columns.map((column, index) => (
          <section key={column.agentId} className="w-[300px] rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-[14px] font-semibold text-[#111827]">{column.agentName}</h3>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${badgeClass(column.status)}`}>
                {column.status}
              </span>
            </div>
            <div className="space-y-1">
              {column.events.map((event) => (
                <p key={event} className="rounded-lg border border-black/[0.06] bg-white px-2 py-1 text-[12px] text-[#344054]">
                  {event}
                </p>
              ))}
            </div>
            {index < columns.length - 1 ? (
              <div className="mt-3 text-center text-[12px] text-[#667085]">Delegates →</div>
            ) : null}
          </section>
        ))}
      </div>
    </div>
  );
}

