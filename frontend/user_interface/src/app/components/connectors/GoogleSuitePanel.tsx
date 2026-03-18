import type { ReactNode } from "react";

import type { ConnectorSummary } from "../../types/connectorSummary";
import { ConnectorServiceList } from "./ConnectorServiceList";

type GoogleSuitePanelProps = {
  connector: ConnectorSummary;
  advancedSettings?: ReactNode;
};

export function GoogleSuitePanel({
  connector,
  advancedSettings,
}: GoogleSuitePanelProps) {
  return (
    <>
      <section className="rounded-2xl border border-black/[0.08] bg-[#f8fafc] p-4">
        <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
          Suite overview
        </p>
        <div className="mt-3 grid grid-cols-3 gap-3">
          <div className="rounded-xl border border-black/[0.06] bg-white px-3 py-2">
            <p className="text-[11px] uppercase tracking-[0.08em] text-[#98a2b3]">Services</p>
            <p className="mt-1 text-[18px] font-semibold text-[#111827]">
              {connector.subServices?.length || 0}
            </p>
          </div>
          <div className="rounded-xl border border-black/[0.06] bg-white px-3 py-2">
            <p className="text-[11px] uppercase tracking-[0.08em] text-[#98a2b3]">Setup</p>
            <p className="mt-1 text-[14px] font-semibold text-[#111827]">OAuth popup</p>
          </div>
          <div className="rounded-xl border border-black/[0.06] bg-white px-3 py-2">
            <p className="text-[11px] uppercase tracking-[0.08em] text-[#98a2b3]">Status</p>
            <p className="mt-1 text-[14px] font-semibold text-[#111827]">{connector.status}</p>
          </div>
        </div>
      </section>

      {connector.subServices?.length ? (
        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
            Google services
          </p>
          <ConnectorServiceList services={connector.subServices} variant="detail" />
        </section>
      ) : null}

      {advancedSettings ? (
        <section className="rounded-2xl border border-black/[0.08] bg-white p-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
            Workspace access
          </p>
          {advancedSettings}
        </section>
      ) : null}
    </>
  );
}
