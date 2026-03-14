type ToolGate = {
  toolId: string;
  requireApproval: boolean;
  timeoutMinutes: number;
  timeoutFallback: "skip" | "cancel" | "proceed";
};

type GateConfigProps = {
  tools: string[];
  gates: ToolGate[];
  onChange: (next: ToolGate[]) => void;
  maxCostBeforePause: number;
  onChangeMaxCostBeforePause: (next: number) => void;
};

function upsertGate(gates: ToolGate[], nextGate: ToolGate): ToolGate[] {
  const index = gates.findIndex((gate) => gate.toolId === nextGate.toolId);
  if (index < 0) {
    return [...gates, nextGate];
  }
  const next = gates.slice();
  next[index] = nextGate;
  return next;
}

function gateForTool(toolId: string, gates: ToolGate[]): ToolGate {
  const existing = gates.find((gate) => gate.toolId === toolId);
  if (existing) {
    return existing;
  }
  return {
    toolId,
    requireApproval: false,
    timeoutMinutes: 60,
    timeoutFallback: "skip",
  };
}

export function GateConfig({
  tools,
  gates,
  onChange,
  maxCostBeforePause,
  onChangeMaxCostBeforePause,
}: GateConfigProps) {
  return (
    <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-3">
        <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Approval gates</p>
        <p className="mt-1 text-[13px] text-[#667085]">Require manual approval for selected tools and cost thresholds.</p>
      </div>

      <label className="mb-4 block">
        <span className="text-[12px] font-semibold text-[#344054]">Pause if LLM cost exceeds (USD)</span>
        <input
          type="number"
          min={0}
          step={0.01}
          value={Number.isFinite(maxCostBeforePause) ? maxCostBeforePause : 0}
          onChange={(event) => onChangeMaxCostBeforePause(Number(event.target.value || 0))}
          className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px] text-[#111827] focus:border-black/[0.28] focus:outline-none"
        />
      </label>

      <div className="space-y-3">
        {tools.map((tool) => {
          const gate = gateForTool(tool, gates);
          return (
            <div key={tool} className="rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3">
              <div className="flex items-center justify-between">
                <p className="text-[13px] font-semibold text-[#111827]">{tool}</p>
                <label className="inline-flex items-center gap-2 text-[12px] text-[#344054]">
                  <input
                    type="checkbox"
                    checked={gate.requireApproval}
                    onChange={(event) =>
                      onChange(
                        upsertGate(gates, {
                          ...gate,
                          requireApproval: event.target.checked,
                        }),
                      )
                    }
                  />
                  Require approval
                </label>
              </div>
              {gate.requireApproval ? (
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <label className="block">
                    <span className="text-[11px] font-semibold text-[#667085]">Timeout (minutes)</span>
                    <input
                      type="number"
                      min={1}
                      step={1}
                      value={gate.timeoutMinutes}
                      onChange={(event) =>
                        onChange(
                          upsertGate(gates, {
                            ...gate,
                            timeoutMinutes: Number(event.target.value || 1),
                          }),
                        )
                      }
                      className="mt-1 w-full rounded-lg border border-black/[0.12] px-2 py-1.5 text-[12px]"
                    />
                  </label>
                  <label className="block">
                    <span className="text-[11px] font-semibold text-[#667085]">On timeout</span>
                    <select
                      value={gate.timeoutFallback}
                      onChange={(event) =>
                        onChange(
                          upsertGate(gates, {
                            ...gate,
                            timeoutFallback: event.target.value as ToolGate["timeoutFallback"],
                          }),
                        )
                      }
                      className="mt-1 w-full rounded-lg border border-black/[0.12] px-2 py-1.5 text-[12px]"
                    >
                      <option value="skip">Skip</option>
                      <option value="cancel">Cancel</option>
                      <option value="proceed">Proceed</option>
                    </select>
                  </label>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export type { ToolGate };

