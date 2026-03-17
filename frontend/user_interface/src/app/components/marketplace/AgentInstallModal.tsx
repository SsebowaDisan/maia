import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";

import {
  preflightMarketplaceAgentInstall,
  type MarketplaceAgentDetail,
} from "../../../api/client";
import { ConnectorBrandIcon } from "../connectors/ConnectorBrandIcon";

type AgentInstallModalProps = {
  open: boolean;
  agent: MarketplaceAgentDetail | null;
  availableConnectorIds: string[];
  installing?: boolean;
  onClose: () => void;
  onOpenConnectorSetup?: (connectorId: string) => void;
  onInstall: (
    agentId: string,
    payload: {
      version?: string | null;
      connector_mapping: Record<string, string>;
      gate_policies: Record<string, boolean>;
    },
  ) => Promise<{
    success: boolean;
    missingConnectors?: string[];
    error?: string;
    triggerFamily?: string | null;
    alreadyInstalled?: boolean;
    autoMappedConnectors?: Record<string, string>;
  }>;
};

type InstallStep = 1 | 2 | 3 | 4;

type InstallOutcome = {
  success: boolean;
  triggerFamily?: string | null;
  error?: string;
  alreadyInstalled?: boolean;
  autoMappedConnectors?: Record<string, string>;
};

type TriggerSummary =
  | {
      family: "scheduled";
      cronExpression: string;
      timezone: string;
      humanText: string;
    }
  | {
      family: "on_event";
      eventType: string;
      sourceConnector: string;
    }
  | {
      family: "manual";
    };

function normalizeLabel(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatHourMinute(hour: number, minute: number): string {
  const safeHour = Math.max(0, Math.min(23, hour));
  const safeMinute = Math.max(0, Math.min(59, minute));
  return `${String(safeHour).padStart(2, "0")}:${String(safeMinute).padStart(2, "0")}`;
}

function describeCronExpression(cronExpression: string): string {
  const parts = String(cronExpression || "").trim().split(/\s+/);
  if (parts.length < 5) {
    return "Custom schedule";
  }
  const [minuteRaw, hourRaw, dayOfMonth, month, dayOfWeek] = parts;
  const minute = Number(minuteRaw);
  const hour = Number(hourRaw);
  const hasFixedTime = Number.isFinite(minute) && Number.isFinite(hour);
  const timeText = hasFixedTime ? formatHourMinute(hour, minute) : "scheduled time";

  const weekdayMap: Record<string, string> = {
    "0": "Sunday",
    "1": "Monday",
    "2": "Tuesday",
    "3": "Wednesday",
    "4": "Thursday",
    "5": "Friday",
    "6": "Saturday",
    "7": "Sunday",
  };

  if (dayOfMonth === "*" && month === "*" && dayOfWeek === "*") {
    return `Every day at ${timeText}`;
  }
  if (dayOfMonth === "*" && month === "*" && weekdayMap[dayOfWeek]) {
    return `Every ${weekdayMap[dayOfWeek]} at ${timeText}`;
  }
  if (month === "*" && dayOfWeek === "*" && dayOfMonth === "1") {
    return `On the first day of each month at ${timeText}`;
  }
  return `Cron schedule: ${cronExpression}`;
}

function readTriggerSummary(definition: Record<string, unknown>): TriggerSummary {
  const trigger = (definition.trigger || {}) as Record<string, unknown>;
  const family = String(trigger.family || "").trim().toLowerCase();
  if (family !== "scheduled") {
    if (family === "on_event") {
      return {
        family: "on_event",
        eventType: String(trigger.event_type || "").trim(),
        sourceConnector: String(trigger.source_connector || "").trim(),
      };
    }
    return { family: "manual" };
  }
  const cronExpression = String(trigger.cron_expression || "").trim();
  const timezone = String(trigger.timezone || "UTC").trim() || "UTC";
  return {
    family: "scheduled",
    cronExpression,
    timezone,
    humanText: describeCronExpression(cronExpression),
  };
}

export function AgentInstallModal({
  open,
  agent,
  availableConnectorIds,
  installing = false,
  onClose,
  onOpenConnectorSetup,
  onInstall,
}: AgentInstallModalProps) {
  const [step, setStep] = useState<InstallStep>(1);
  const [connectorMap, setConnectorMap] = useState<Record<string, string>>({});
  const [gateEnabled, setGateEnabled] = useState<Record<string, boolean>>({});
  const [installOutcome, setInstallOutcome] = useState<InstallOutcome | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [preflightError, setPreflightError] = useState("");
  const [preflight, setPreflight] = useState<{
    can_install_immediately: boolean;
    already_installed: boolean;
    missing_connectors: string[];
    auto_mapped: Record<string, string>;
    agent_not_found: boolean;
  } | null>(null);
  const [customizeMode, setCustomizeMode] = useState(false);
  const [waitingForConnector, setWaitingForConnector] = useState(false);
  const [connectorSheetMessage, setConnectorSheetMessage] = useState("");
  const autoInstallInProgressRef = useRef(false);

  const requiredConnectors = agent?.required_connectors || [];
  const triggerSummary = useMemo(
    () => readTriggerSummary((agent?.definition || {}) as Record<string, unknown>),
    [agent?.definition],
  );

  const fallbackMissingConnectors = useMemo(
    () => requiredConnectors.filter((required) => !availableConnectorIds.includes(required)),
    [availableConnectorIds, requiredConnectors],
  );

  const missingConnectors = useMemo(() => {
    if (Array.isArray(preflight?.missing_connectors)) {
      return preflight.missing_connectors;
    }
    return fallbackMissingConnectors;
  }, [fallbackMissingConnectors, preflight?.missing_connectors]);

  const singleMissingConnector = missingConnectors.length === 1 ? missingConnectors[0] : "";

  const showSingleConnectorSheet =
    step < 4 &&
    !customizeMode &&
    !preflightLoading &&
    !preflight?.can_install_immediately &&
    !preflight?.already_installed &&
    missingConnectors.length === 1;

  const refreshPreflight = useCallback(async () => {
    if (!agent?.agent_id) {
      return null;
    }
    setPreflightLoading(true);
    try {
      const next = await preflightMarketplaceAgentInstall(agent.agent_id, {
        version: agent.version,
      });
      setPreflight(next);
      setPreflightError("");
      return next;
    } catch (error) {
      const message = String(error || "Failed to check install prerequisites.");
      setPreflightError(message);
      return null;
    } finally {
      setPreflightLoading(false);
    }
  }, [agent?.agent_id, agent?.version]);

  const runInstall = useCallback(
    async (explicitConnectorMap?: Record<string, string>) => {
      if (!agent?.agent_id) {
        return;
      }
      const mapping =
        explicitConnectorMap ||
        (Object.keys(connectorMap).length > 0 ? connectorMap : preflight?.auto_mapped || {});
      const result = await onInstall(agent.agent_id, {
        version: agent.version,
        connector_mapping: mapping,
        gate_policies: gateEnabled,
      });
      if (!result.success) {
        setInstallOutcome({
          success: false,
          error:
            result.error ||
            (Array.isArray(result.missingConnectors) && result.missingConnectors.length
              ? `Missing connectors: ${result.missingConnectors.join(", ")}`
              : "Install failed."),
          triggerFamily: result.triggerFamily || null,
          alreadyInstalled: Boolean(result.alreadyInstalled),
          autoMappedConnectors: result.autoMappedConnectors || {},
        });
        const refreshed = await refreshPreflight();
        if (refreshed) {
          setPreflight(refreshed);
        }
        return;
      }
      setInstallOutcome({
        success: true,
        triggerFamily: result.triggerFamily || null,
        alreadyInstalled: Boolean(result.alreadyInstalled),
        autoMappedConnectors: result.autoMappedConnectors || {},
        error: "",
      });
      setStep(4);
      setWaitingForConnector(false);
      setConnectorSheetMessage("");
    },
    [agent?.agent_id, agent?.version, connectorMap, gateEnabled, onInstall, preflight?.auto_mapped, refreshPreflight],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setStep(1);
    setConnectorMap({});
    setGateEnabled({});
    setInstallOutcome(null);
    setPreflight(null);
    setPreflightError("");
    setCustomizeMode(false);
    setWaitingForConnector(false);
    setConnectorSheetMessage("");
    autoInstallInProgressRef.current = false;
    void refreshPreflight();
  }, [open, agent?.agent_id, refreshPreflight]);

  useEffect(() => {
    if (!open || !agent?.agent_id || !waitingForConnector) {
      return;
    }
    let cancelled = false;
    const startedAt = Date.now();

    const poll = async () => {
      if (cancelled || autoInstallInProgressRef.current) {
        return;
      }
      const next = await refreshPreflight();
      if (!next || cancelled) {
        return;
      }
      if (next.can_install_immediately) {
        autoInstallInProgressRef.current = true;
        setConnectorSheetMessage("Connector detected. Installing automatically...");
        await runInstall(next.auto_mapped || {});
        autoInstallInProgressRef.current = false;
        return;
      }
      if (Date.now() - startedAt > 120000) {
        setWaitingForConnector(false);
        setConnectorSheetMessage("Still waiting for connector setup. Finish setup and click Check again.");
      }
    };

    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, 2500);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [open, agent?.agent_id, refreshPreflight, runInstall, waitingForConnector]);

  if (!open || !agent) {
    return null;
  }

  const next = () => setStep((previous) => Math.min(4, (previous + 1) as InstallStep));
  const back = () => setStep((previous) => Math.max(1, (previous - 1) as InstallStep));

  const autoMappedEntries = Object.entries(installOutcome?.autoMappedConnectors || {});

  return (
    <div className="fixed inset-0 z-[150] bg-black/35 backdrop-blur-[3px]">
      <div className="absolute left-1/2 top-1/2 w-[min(880px,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-[26px] border border-black/[0.08] bg-white shadow-[0_30px_80px_rgba(15,23,42,0.28)]">
        <div className="flex items-start justify-between border-b border-black/[0.08] px-6 py-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#667085]">
              Install agent
            </p>
            <h3 className="mt-1 text-[22px] font-semibold text-[#101828]">{agent.name}</h3>
            <p className="mt-1 text-[13px] text-[#667085]">
              {showSingleConnectorSheet ? "Connector setup required" : `Step ${step} of 4`}
            </p>
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
          {preflightError ? (
            <p className="rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#b42318]">
              {preflightError}
            </p>
          ) : null}

          {showSingleConnectorSheet ? (
            <section>
              <h4 className="text-[16px] font-semibold text-[#111827]">Quick connector setup</h4>
              <p className="mt-1 text-[13px] text-[#667085]">
                This agent needs {normalizeLabel(singleMissingConnector)} before it can be installed.
              </p>
              <div className="mt-3 rounded-xl border border-[#fde68a] bg-[#fffbeb] px-3 py-2.5">
                <p className="text-[12px] text-[#92400e]">
                  Complete connector auth in the popup. Installation will continue automatically once connected.
                </p>
              </div>
              {connectorSheetMessage ? (
                <p className="mt-2 text-[12px] text-[#475467]">{connectorSheetMessage}</p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (!singleMissingConnector) {
                      return;
                    }
                    onOpenConnectorSetup?.(singleMissingConnector);
                    setWaitingForConnector(true);
                    setConnectorSheetMessage(
                      `Waiting for ${normalizeLabel(singleMissingConnector)} setup...`,
                    );
                  }}
                  disabled={installing || preflightLoading || waitingForConnector}
                  className="rounded-full bg-[#7c3aed] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-60"
                >
                  {waitingForConnector ? "Waiting for connector..." : "Connect"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setWaitingForConnector(false);
                    void refreshPreflight();
                  }}
                  disabled={installing || preflightLoading}
                  className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[13px] font-semibold text-[#344054] disabled:opacity-60"
                >
                  Check again
                </button>
                <button
                  type="button"
                  onClick={() => setCustomizeMode(true)}
                  className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[13px] font-semibold text-[#344054]"
                >
                  Customise
                </button>
              </div>
            </section>
          ) : null}

          {!showSingleConnectorSheet && step === 1 ? (
            <section>
              <h4 className="text-[16px] font-semibold text-[#111827]">Review access</h4>
              <p className="mt-1 text-[13px] text-[#667085]">{agent.description}</p>
              <ul className="mt-3 space-y-1.5 text-[13px] text-[#475467]">
                {requiredConnectors.map((connector) => (
                  <li key={connector} className="flex items-center gap-2">
                    <ConnectorBrandIcon
                      connectorId={connector}
                      label={normalizeLabel(connector)}
                      size={18}
                    />
                    <span>{normalizeLabel(connector)}</span>
                  </li>
                ))}
              </ul>
              {triggerSummary.family === "scheduled" ? (
                <div className="mt-3 rounded-xl border border-[#c4b5fd] bg-[#f5f3ff] px-3 py-2.5">
                  <p className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[#7c3aed]">
                    Runs automatically
                  </p>
                  <p className="mt-1 text-[13px] font-medium text-[#1e3a8a]">
                    {triggerSummary.humanText}
                  </p>
                  <p className="mt-1 text-[12px] text-[#5b21b6]">Timezone: {triggerSummary.timezone}</p>
                  <p className="mt-1 text-[12px] text-[#5b21b6]">
                    The schedule starts immediately after installation.
                  </p>
                  {triggerSummary.cronExpression ? (
                    <p className="mt-1 text-[11px] text-[#5b21b6]">
                      Cron: <code>{triggerSummary.cronExpression}</code>
                    </p>
                  ) : null}
                </div>
              ) : null}
              {triggerSummary.family === "on_event" ? (
                <div className="mt-3 rounded-xl border border-[#fde68a] bg-[#fffbeb] px-3 py-2.5">
                  <p className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[#92400e]">
                    Event-triggered
                  </p>
                  <p className="mt-1 text-[13px] font-medium text-[#78350f]">
                    Triggers on: {triggerSummary.eventType || "event"} from {" "}
                    {triggerSummary.sourceConnector || "connector"}
                  </p>
                </div>
              ) : null}
              {triggerSummary.family === "manual" ? (
                <div className="mt-3 rounded-xl border border-[#d0d5dd] bg-[#f8fafc] px-3 py-2.5">
                  <p className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[#475467]">
                    Manual run
                  </p>
                  <p className="mt-1 text-[12px] text-[#667085]">
                    This agent does not auto-run. Start it manually or invoke it from a workflow.
                  </p>
                </div>
              ) : null}
            </section>
          ) : null}

          {!showSingleConnectorSheet && step === 2 ? (
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
                <div className="mt-2 rounded-xl border border-[#fecaca] bg-[#fff1f2] p-3">
                  <p className="text-[12px] font-semibold text-[#b42318]">Missing connector support</p>
                  <div className="mt-2 space-y-1.5">
                    {missingConnectors.map((connectorId) => (
                      <div
                        key={connectorId}
                        className="flex items-center justify-between gap-2 rounded-lg border border-[#fecdd3] bg-white px-2.5 py-1.5"
                      >
                        <span className="inline-flex items-center gap-2 text-[12px] text-[#7a271a]">
                          <ConnectorBrandIcon
                            connectorId={connectorId}
                            label={normalizeLabel(connectorId)}
                            size={18}
                          />
                          {normalizeLabel(connectorId)}
                        </span>
                        <button
                          type="button"
                          onClick={() => onOpenConnectorSetup?.(connectorId)}
                          className="rounded-full border border-[#fca5a5] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#9f1239] hover:bg-[#fff1f2]"
                        >
                          Connect
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>
          ) : null}

          {!showSingleConnectorSheet && step === 3 ? (
            <section>
              <h4 className="text-[16px] font-semibold text-[#111827]">Gate preferences</h4>
              <div className="mt-2 rounded-xl border border-[#d0d5dd] bg-[#f8fafc] px-3 py-2.5">
                <p className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[#475467]">
                  What this means
                </p>
                <p className="mt-1 text-[12px] text-[#667085]">
                  A gate pauses the agent before it performs a real action, so you can approve or reject it first.
                </p>
              </div>
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
                    Require approval before {normalizeLabel(required)} actions
                  </label>
                ))}
              </div>
            </section>
          ) : null}

          {step === 4 ? (
            <section>
              <h4 className="text-[16px] font-semibold text-[#111827]">
                {installOutcome?.alreadyInstalled ? "Agent already installed" : "Agent installed"}
              </h4>
              <p className="mt-1 text-[13px] text-[#667085]">
                {(() => {
                  if (installOutcome?.alreadyInstalled) {
                    return "This version is already available in your workspace.";
                  }
                  const normalizedFamily = String(
                    installOutcome?.triggerFamily || triggerSummary.family || "",
                  )
                    .trim()
                    .toLowerCase();
                  if (normalizedFamily === "scheduled") {
                    return "Your agent is set up and will run automatically. You can also add it to a workflow.";
                  }
                  if (normalizedFamily === "conversational") {
                    return "Your agent is ready. Chat with it now or add it to a workflow.";
                  }
                  return "Your agent is ready. You can close this modal or add it to a workflow.";
                })()}
              </p>
              {installOutcome?.error ? (
                <p className="mt-2 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#b42318]">
                  {installOutcome.error}
                </p>
              ) : null}
              {autoMappedEntries.length > 0 ? (
                <div className="mt-3">
                  <p className="text-[12px] font-semibold text-[#166534]">Connected automatically</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {autoMappedEntries.map(([requiredId, mappedId]) => (
                      <span
                        key={`${requiredId}:${mappedId}`}
                        className="rounded-full border border-[#bbf7d0] bg-[#ecfdf3] px-2 py-0.5 text-[11px] font-semibold text-[#166534]"
                      >
                        {requiredId} {"->"} {mappedId}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>
          ) : null}
        </div>

        <div className="flex items-center justify-between border-t border-black/[0.08] px-6 py-4">
          {step < 4 ? (
            <button
              type="button"
              onClick={back}
              disabled={step === 1 || installing || showSingleConnectorSheet}
              className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[13px] font-semibold text-[#344054] disabled:opacity-40"
            >
              Back
            </button>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[13px] font-semibold text-[#344054]"
            >
              Done
            </button>
          )}
          {showSingleConnectorSheet ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[13px] font-semibold text-[#344054]"
            >
              Close
            </button>
          ) : step < 3 ? (
            <button
              type="button"
              onClick={next}
              disabled={installing || (step === 2 && missingConnectors.length > 0)}
              className="rounded-full bg-[#7c3aed] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-60"
            >
              Next
            </button>
          ) : step === 3 ? (
            <button
              type="button"
              disabled={installing}
              onClick={() => {
                void runInstall();
              }}
              className="rounded-full bg-[#7c3aed] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-60"
            >
              {installing ? "Installing..." : "Install agent"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                const query = new URLSearchParams({
                  open_picker: "1",
                  agent: agent.agent_id,
                });
                window.history.pushState({}, "", `/workflow-builder?${query.toString()}`);
                window.dispatchEvent(new PopStateEvent("popstate"));
                onClose();
              }}
              className="rounded-full bg-[#7c3aed] px-4 py-2 text-[13px] font-semibold text-white"
            >
              Add to workflow
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
