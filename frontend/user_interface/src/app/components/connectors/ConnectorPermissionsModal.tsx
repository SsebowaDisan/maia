import { X } from "lucide-react";

import { ToolPermissionMatrix } from "./ToolPermissionMatrix";
import type { ConnectorSummary } from "../../types/connectorSummary";

type ConnectorPermissionsModalProps = {
  open: boolean;
  connectors: ConnectorSummary[];
  agents: Array<{
    id: string;
    name: string;
  }>;
  value: Record<string, string[]>;
  savingConnectorId?: string | null;
  error?: string;
  onClose: () => void;
  onChange: (next: Record<string, string[]>) => void;
};

export function ConnectorPermissionsModal({
  open,
  connectors,
  agents,
  value,
  savingConnectorId = null,
  error = "",
  onClose,
  onChange,
}: ConnectorPermissionsModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[130] bg-black/30 backdrop-blur-md">
      <div className="absolute left-1/2 top-1/2 max-h-[86vh] w-[min(1080px,94vw)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[20px] border border-white/20 bg-white/95 shadow-[0_24px_80px_-16px_rgba(0,0,0,0.22),0_8px_24px_-8px_rgba(0,0,0,0.10)] backdrop-blur-2xl">
        <div className="flex items-start justify-between border-b border-black/[0.06] bg-white/60 px-5 py-4 backdrop-blur-xl">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7c3aed]">
              Access control
            </p>
            <h2 className="mt-1 text-[20px] font-semibold text-[#1d1d1f]">
              Agent permissions
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#86868b] transition-colors hover:bg-black/[0.05] hover:text-[#1d1d1f]"
            aria-label="Close permissions"
          >
            <X size={15} />
          </button>
        </div>

        <div className="space-y-3 overflow-y-auto px-5 py-4">
          {savingConnectorId ? (
            <p className="text-[12px] text-[#667085]">
              Saving permission update for {savingConnectorId}...
            </p>
          ) : null}
          {error ? (
            <p className="rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
              {error}
            </p>
          ) : null}

          <ToolPermissionMatrix
            agents={agents}
            connectors={connectors}
            value={value}
            onChange={onChange}
          />
        </div>
      </div>
    </div>
  );
}
