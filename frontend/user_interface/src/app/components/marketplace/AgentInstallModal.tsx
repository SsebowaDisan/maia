import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";

import type { MarketplaceAgentDetail } from "../../../api/client";

type AgentInstallModalProps = {
  open: boolean;
  agent: MarketplaceAgentDetail | null;
  availableConnectorIds: string[];
  installing?: boolean;
  onClose: () => void;
  onInstall: (
    agentId: string,
    payload: { version?: string | null; connector_mapping: Record<string, string> },
  ) => Promise<void> | void;
};

type InstallStep = 1 | 2 | 3 | 4;

function normalizeLabel(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function AgentInstallModal({
  open,
  agent,
  availableConnectorIds,
  installing = false,
  onClose,
  onInstall,
}: AgentInstallModalProps) {
  const [step, setStep] = useState<InstallStep>(1);
  const [connectorMap, setConnectorMap] = useState<Record<string, string>>({});
  const [gateEnabled, setGateEnabled] = useState<Record<string, boolean>>({});

  const requiredConnectors = agent?.required_connectors || [];
  const missingConnectors = useMemo(
    () => requiredConnectors.filter((required) => !availableConnectorIds.includes(required)),
    [availableConnectorIds, requiredConnectors],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setStep(1);
    setConnectorMap({});
    setGateEnabled({});
  }, [open, agent?.agent_id]);

  if (!open || !agent) {
    return null;
  }

  const next = () => setStep((previous) => Math.min(4, (previous + 1) as InstallStep));
  const back = () => setStep((previous) => Math.max(1, (previous - 1) as InstallStep));

  return (
    <div className="fixed inset-0 z-[150] bg-black/35 backdrop-blur-[3px]">
      <div className="absolute left-1/2 top-1/2 w-[min(880px,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-[26px] border border-black/[0.08] bg-white shadow-[0_30px_80px_rgba(15,23,42,0.28)]">
        <div className="flex items-start justify-between border-b border-black/[0.08] px-6 py-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#667085]">
              Install agent
            </p>
            <h3 className="mt-1 text-[22px] font-semibold text-[#101828]">{agent.name}</h3>
            <p className="mt-1 text-[13px] text-[#667085]">Step {step} of 4</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-black/[0.1] text-[#667085]"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          {step === 1 ? (
            <section>
              <h4 className="text-[16px] font-semibold text-[#111827]">Review access</h4>
              <p className="mt-1 text-[13px] text-[#667085]">{agent.description}</p>
              <ul className="mt-3 list-disc space-y-1 pl-4 text-[13px] text-[#475467]">
                {requiredConnectors.map((connector) => (
                  <li key={connector}>{normalizeLabel(connector)}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {step === 2 ? (
            <section>
              <h4 className="text-[16px] font-semibold text-[#111827]">Map required connectors</h4>
              <div className="mt-3 space-y-2">
                {requiredConnectors.map((required) => (
                  <label key={required} className="block">
                    <span className="text-[12px] font-semibold text-[#667085]">
                      {normalizeLabel(required)}
                    </span>
                    <select
                      value={connectorMap[required] || ""}
                      onChange={(event) =>
                        setConnectorMap((previous) => ({
                          ...previous,
                          [required]: event.target.value,
                        }))
                      }
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    >
                      <option value="">Auto-map to {required}</option>
                      {availableConnectorIds.map((connectorId) => (
                        <option key={connectorId} value={connectorId}>
                          {normalizeLabel(connectorId)} ({connectorId})
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              {missingConnectors.length ? (
                <p className="mt-2 text-[12px] text-[#b42318]">
                  Missing connector support: {missingConnectors.map(normalizeLabel).join(", ")}
                </p>
              ) : null}
            </section>
          ) : null}

          {step === 3 ? (
            <section>
              <h4 className="text-[16px] font-semibold text-[#111827]">Gate preferences</h4>
              <div className="mt-3 space-y-2">
                {requiredConnectors.map((required) => (
                  <label key={required} className="flex items-center gap-2 text-[13px] text-[#344054]">
                    <input
                      type="checkbox"
                      checked={Boolean(gateEnabled[required])}
                      onChange={(event) =>
                        setGateEnabled((previous) => ({
                          ...previous,
                          [required]: event.target.checked,
                        }))
                      }
                    />
                    Require approval for {normalizeLabel(required)} actions
                  </label>
                ))}
              </div>
            </section>
          ) : null}

          {step === 4 ? (
            <section>
              <h4 className="text-[16px] font-semibold text-[#111827]">Confirm install</h4>
              <p className="mt-1 text-[13px] text-[#667085]">
                Install version {agent.version} with {Object.keys(connectorMap).length} connector mappings and{" "}
                {Object.values(gateEnabled).filter(Boolean).length} gate policies.
              </p>
            </section>
          ) : null}
        </div>

        <div className="flex items-center justify-between border-t border-black/[0.08] px-6 py-4">
          <button
            type="button"
            onClick={back}
            disabled={step === 1 || installing}
            className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[13px] font-semibold text-[#344054] disabled:opacity-40"
          >
            Back
          </button>
          {step < 4 ? (
            <button
              type="button"
              onClick={next}
              disabled={installing}
              className="rounded-full bg-[#111827] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-60"
            >
              Next
            </button>
          ) : (
            <button
              type="button"
              disabled={installing}
              onClick={() =>
                onInstall(agent.agent_id, {
                  version: agent.version,
                  connector_mapping: connectorMap,
                })
              }
              className="rounded-full bg-[#111827] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-60"
            >
              {installing ? "Installing..." : "Install agent"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
