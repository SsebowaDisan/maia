import { ConnectorBrandIcon } from "./ConnectorBrandIcon";
import { ConnectorServiceList } from "./ConnectorServiceList";
import { ConnectorSetupStatusBadge } from "./ConnectorSetupStatusBadge";
import { primaryActionLabel } from "./catalogModel";
import type { ConnectorSummary } from "../../types/connectorSummary";

type ConnectorCatalogCardProps = {
  connector: ConnectorSummary;
  onOpen: (connectorId: string) => void;
};

export function ConnectorCatalogCard({
  connector,
  onOpen,
}: ConnectorCatalogCardProps) {
  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(connector.id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(connector.id);
        }
      }}
      className="group rounded-2xl border border-black/[0.06] bg-white p-4 transition-all hover:border-[#c4b5fd] hover:shadow-[0_8px_24px_rgba(124,58,237,0.08)]"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-black/[0.06] bg-[#fafafa]">
          <ConnectorBrandIcon
            connectorId={connector.id}
            brandSlug={connector.brandSlug}
            label={connector.name}
            size={20}
          />
        </div>
        <ConnectorSetupStatusBadge status={connector.status} />
      </div>

      <h3 className="mt-3 text-[16px] font-semibold tracking-[-0.01em] text-[#1d1d1f]">
        {connector.name}
      </h3>
      <p className="mt-1 min-h-[36px] text-[12px] leading-[1.5] text-[#86868b]">
        {connector.description}
      </p>

      {connector.subServices?.length ? (
        <div className="mt-3">
          <ConnectorServiceList services={connector.subServices} />
        </div>
      ) : null}

      <div className="mt-3 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] text-[#c7c7cc]">
            {connector.authType}
            {typeof connector.actionsCount === "number" && connector.actionsCount > 0
              ? ` | ${connector.actionsCount} actions`
              : ""}
          </p>
          {connector.statusMessage ? (
            <p className="mt-1 line-clamp-2 text-[11px] text-[#667085]">
              {connector.statusMessage}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onOpen(connector.id);
          }}
          className="shrink-0 rounded-full bg-[#f5f3ff] px-3 py-1.5 text-[12px] font-medium text-[#7c3aed] transition-colors hover:bg-[#ede9fe]"
        >
          {primaryActionLabel(connector.status)}
        </button>
      </div>
    </article>
  );
}
