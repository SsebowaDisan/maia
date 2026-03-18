import type { ReactNode } from "react";

import type { ConnectorSummary } from "../../types/connectorSummary";
import { ConnectorServiceList } from "./ConnectorServiceList";

type MicrosoftSuitePanelProps = {
  connector: ConnectorSummary;
  setupPanel: ReactNode;
};

export function MicrosoftSuitePanel({
  connector,
  setupPanel,
}: MicrosoftSuitePanelProps) {
  return (
    <>
      <section className="rounded-2xl border border-black/[0.08] bg-[#f8fafc] p-4">
        <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
          Suite overview
        </p>
        <p className="mt-2 text-[13px] text-[#667085]">
          Microsoft 365 groups Outlook, Calendar, OneDrive, Excel, Word, and Teams under one workspace connection. This drawer is ready for both the current manual-token flow and a later OAuth upgrade.
        </p>
      </section>

      {connector.subServices?.length ? (
        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <p className="mb-3 text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
            Microsoft services
          </p>
          <ConnectorServiceList services={connector.subServices} variant="detail" />
        </section>
      ) : null}

      {setupPanel}
    </>
  );
}
