import { X } from "lucide-react";

import type { ConnectorSummary } from "../../types/connectorSummary";
import { ConnectorBrandIcon } from "./ConnectorBrandIcon";

type ConnectorDetailHeaderProps = {
  connector: ConnectorSummary;
  onClose: () => void;
};

function formatLabel(value?: string) {
  if (!value) {
    return null;
  }
  return value
    .split(/[_-]+/g)
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

export function ConnectorDetailHeader({
  connector,
  onClose,
}: ConnectorDetailHeaderProps) {
  const meta = [
    connector.suiteLabel || formatLabel(connector.suiteId),
    formatLabel(connector.setupMode),
    formatLabel(connector.sceneFamily),
  ].filter(Boolean);

  return (
    <div className="border-b border-black/[0.08] px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <div className="inline-flex h-11 w-11 items-center justify-center rounded-[14px] border border-black/[0.06] bg-[#fafafa]">
              <ConnectorBrandIcon
                connectorId={connector.id}
                brandSlug={connector.brandSlug}
                label={connector.name}
                size={22}
              />
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#667085]">
                Connector detail
              </p>
              <h2 className="truncate text-[24px] font-semibold tracking-[-0.02em] text-[#101828]">
                {connector.name}
              </h2>
            </div>
          </div>
          <p className="mt-3 text-[13px] text-[#667085]">{connector.description}</p>
          {meta.length ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {meta.map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-black/[0.08] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-medium text-[#475467]"
                >
                  {item}
                </span>
              ))}
            </div>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-black/[0.1] text-[#475467] hover:text-[#111827]"
          aria-label="Close connector details"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
