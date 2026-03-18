import { RefreshCw } from "lucide-react";

type ConnectorDetailActionsProps = {
  canRevoke: boolean;
  disabled?: boolean;
  onTest: () => void;
  onRevoke: () => void;
};

export function ConnectorDetailActions({
  canRevoke,
  disabled = false,
  onTest,
  onRevoke,
}: ConnectorDetailActionsProps) {
  return (
    <div className={`grid gap-3 ${canRevoke ? "grid-cols-2" : "grid-cols-1"}`}>
      <button
        type="button"
        onClick={onTest}
        disabled={disabled}
        className="inline-flex items-center justify-center gap-2 rounded-xl border border-black/[0.12] bg-white px-3 py-2 text-[13px] font-semibold text-[#111827] hover:border-black/[0.24] disabled:cursor-not-allowed disabled:opacity-60"
      >
        <RefreshCw size={13} />
        Test connection
      </button>
      {canRevoke ? (
        <button
          type="button"
          onClick={onRevoke}
          disabled={disabled}
          className="inline-flex items-center justify-center rounded-xl border border-[#fda4af] bg-[#fff1f2] px-3 py-2 text-[13px] font-semibold text-[#9f1239] hover:bg-[#ffe4e6] disabled:cursor-not-allowed disabled:opacity-60"
        >
          Revoke
        </button>
      ) : null}
    </div>
  );
}
