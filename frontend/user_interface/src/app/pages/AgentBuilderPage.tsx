import { useMemo, useState } from "react";

import { GateConfig, type ToolGate } from "../components/agentBuilder/GateConfig";
import { SystemPromptEditor } from "../components/agentBuilder/SystemPromptEditor";
import { ToolSelector } from "../components/agentBuilder/ToolSelector";
import { AGENT_OS_CONNECTORS } from "./agentOsData";

type BuilderMode = "visual" | "yaml";

type AgentDraft = {
  agent_id: string;
  version: string;
  name: string;
  description: string;
  system_prompt: string;
  tools: string[];
  memory: {
    working_enabled: boolean;
    episodic_enabled: boolean;
    semantic_enabled: boolean;
  };
  triggers: Array<{ type: "conversational" | "schedule" | "event"; value: string }>;
  gates: ToolGate[];
  output_block_types: string[];
  max_delegation_depth: number;
  cost_gate_usd: number;
};

const OUTPUT_BLOCK_OPTIONS = ["text", "markdown", "math", "code", "table", "widget"];

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function AgentBuilderPage() {
  const [mode, setMode] = useState<BuilderMode>("visual");
  const [yamlError, setYamlError] = useState("");
  const [draft, setDraft] = useState<AgentDraft>({
    agent_id: "new-agent",
    version: "1.0.0",
    name: "New Agent",
    description: "Describe the agent purpose.",
    system_prompt: "You are an assistant focused on high-signal operational output.",
    tools: [],
    memory: {
      working_enabled: true,
      episodic_enabled: true,
      semantic_enabled: true,
    },
    triggers: [{ type: "conversational", value: "default" }],
    gates: [],
    output_block_types: ["markdown", "table"],
    max_delegation_depth: 2,
    cost_gate_usd: 0.5,
  });

  const [yamlText, setYamlText] = useState(prettyJson(draft));

  const syncYamlFromDraft = (nextDraft: AgentDraft) => {
    setDraft(nextDraft);
    setYamlText(prettyJson(nextDraft));
    setYamlError("");
  };

  const parsedPreview = useMemo(() => prettyJson(draft), [draft]);

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1240px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Agent builder</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Create and configure agents</h1>
          <p className="mt-2 text-[15px] text-[#475467]">Switch between visual and schema editing modes with synchronized state.</p>
          <div className="mt-4 flex gap-2">
            {(["visual", "yaml"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={`rounded-full px-4 py-2 text-[13px] font-semibold capitalize ${
                  mode === value ? "bg-[#111827] text-white" : "border border-black/[0.12] bg-white text-[#344054]"
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </section>

        {mode === "visual" ? (
          <section className="grid grid-cols-1 gap-4 xl:grid-cols-[1.05fr_0.95fr]">
            <div className="space-y-4">
              <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Identity</p>
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Agent ID</span>
                    <input
                      value={draft.agent_id}
                      onChange={(event) => syncYamlFromDraft({ ...draft, agent_id: event.target.value })}
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Version</span>
                    <input
                      value={draft.version}
                      onChange={(event) => syncYamlFromDraft({ ...draft, version: event.target.value })}
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Name</span>
                    <input
                      value={draft.name}
                      onChange={(event) => syncYamlFromDraft({ ...draft, name: event.target.value })}
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Description</span>
                    <input
                      value={draft.description}
                      onChange={(event) => syncYamlFromDraft({ ...draft, description: event.target.value })}
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                </div>
              </div>

              <SystemPromptEditor
                value={draft.system_prompt}
                onChange={(next) => syncYamlFromDraft({ ...draft, system_prompt: next })}
              />

              <ToolSelector
                connectors={AGENT_OS_CONNECTORS}
                selectedTools={draft.tools}
                onChange={(next) => syncYamlFromDraft({ ...draft, tools: next })}
              />
            </div>

            <div className="space-y-4">
              <GateConfig
                tools={draft.tools}
                gates={draft.gates}
                onChange={(next) => syncYamlFromDraft({ ...draft, gates: next })}
                maxCostBeforePause={draft.cost_gate_usd}
                onChangeMaxCostBeforePause={(next) => syncYamlFromDraft({ ...draft, cost_gate_usd: next })}
              />

              <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Output blocks</p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {OUTPUT_BLOCK_OPTIONS.map((option) => {
                    const checked = draft.output_block_types.includes(option);
                    return (
                      <label key={option} className="inline-flex items-center gap-2 text-[13px] text-[#344054]">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(event) => {
                            const next = event.target.checked
                              ? [...draft.output_block_types, option]
                              : draft.output_block_types.filter((type) => type !== option);
                            syncYamlFromDraft({ ...draft, output_block_types: next });
                          }}
                        />
                        {option}
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Runtime controls</p>
                <label className="mt-3 block">
                  <span className="text-[12px] font-semibold text-[#344054]">Max delegation depth</span>
                  <input
                    type="number"
                    min={1}
                    max={8}
                    value={draft.max_delegation_depth}
                    onChange={(event) =>
                      syncYamlFromDraft({
                        ...draft,
                        max_delegation_depth: Number(event.target.value || 1),
                      })
                    }
                    className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                  />
                </label>
              </div>
            </div>
          </section>
        ) : (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">YAML / JSON editor</p>
            <textarea
              value={yamlText}
              onChange={(event) => setYamlText(event.target.value)}
              className="h-[460px] w-full resize-none rounded-xl border border-black/[0.12] bg-[#0b1020] px-3 py-2 font-mono text-[12px] leading-[1.55] text-[#d1e0ff]"
            />
            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  try {
                    const parsed = JSON.parse(yamlText) as AgentDraft;
                    syncYamlFromDraft(parsed);
                  } catch (error) {
                    setYamlError(`Invalid JSON: ${String(error)}`);
                  }
                }}
                className="rounded-full bg-[#111827] px-4 py-2 text-[13px] font-semibold text-white"
              >
                Apply editor changes
              </button>
              {yamlError ? <span className="text-[12px] text-[#b42318]">{yamlError}</span> : null}
            </div>
          </section>
        )}

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Compiled definition preview</p>
          <pre className="mt-2 overflow-x-auto rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3 text-[12px] text-[#344054]">
            <code>{parsedPreview}</code>
          </pre>
        </section>
      </div>
    </div>
  );
}

