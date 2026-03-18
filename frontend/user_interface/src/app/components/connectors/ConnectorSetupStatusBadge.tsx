import type { ConnectorStatus } from "../../types/connectorSummary";

type ConnectorSetupStatusBadgeProps = {
  status: ConnectorStatus;
};

function statusClass(status: ConnectorStatus): string {
  if (status === "Connected") {
    return "border-[#c7ead8] bg-[#edf9f2] text-[#166534]";
  }
  if (status === "Needs permission") {
    return "border-[#fbd38d] bg-[#fff7ed] text-[#9a3412]";
  }
  if (status === "Expired") {
    return "border-[#fbd38d] bg-[#fff7ed] text-[#9a3412]";
  }
  return "border-[#d0d5dd] bg-[#f8fafc] text-[#475467]";
}

export function ConnectorSetupStatusBadge({
  status,
}: ConnectorSetupStatusBadgeProps) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${statusClass(
        status,
      )}`}
    >
      {status}
    </span>
  );
}
