import type { ConnectorSummary } from "../../pages/agentOsData";

type ToolSelectorProps = {
  connectors: ConnectorSummary[];
  selectedTools: string[];
  onChange: (next: string[]) => void;
};

function toggleTool(selected: string[], toolId: string): string[] {
  if (selected.includes(toolId)) {
    return selected.filter((entry) => entry !== toolId);
  }
  return [...selected, toolId];
}

export function ToolSelector({ connectors, selectedTools, onChange }: ToolSelectorProps) {
  return (
    <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Tools</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {selectedTools.map((tool) => (
          <span key={tool} className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[12px] text-[#344054]">
            {tool}
          </span>
        ))}
        {!selectedTools.length ? (
          <span className="rounded-full border border-[#f2f4f7] bg-[#fcfcfd] px-2.5 py-1 text-[12px] text-[#98a2b3]">
            No tools selected
          </span>
        ) : null}
      </div>
      <div className="mt-4 space-y-4">
        {connectors.map((connector) => {
          const blocked = connector.status !== "Connected";
          return (
            <section key={connector.id}>
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-[14px] font-semibold text-[#111827]">{connector.name}</h4>
                <span className={`text-[11px] ${blocked ? "text-[#b42318]" : "text-[#027a48]"}`}>
                  {blocked ? "Connect first" : "Ready"}
                </span>
              </div>
              <div className="space-y-2">
                {connector.tools.map((tool) => {
                  const checked = selectedTools.includes(tool);
                  return (
                    <label key={tool} className="flex items-center gap-2 text-[13px] text-[#344054]">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={blocked}
                        onChange={() => onChange(toggleTool(selectedTools, tool))}
                        className="h-4 w-4 rounded border border-black/[0.2]"
                      />
                      <span>{tool}</span>
                    </label>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

