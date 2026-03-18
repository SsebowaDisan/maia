/**
 * StepTypeConfig — per-type configuration panels for deterministic nodes.
 * Renders the right config fields based on step_type.
 */
import { useState } from "react";
import type { StepType } from "../../stores/workflowStore";

type StepTypeConfigProps = {
  stepType: StepType;
  stepConfig: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
};

function StepTypeConfig({ stepType, stepConfig, onChange }: StepTypeConfigProps) {
  if (stepType === "agent") return null;

  const renderers: Record<string, () => React.ReactNode> = {
    http_request: () => <HttpRequestConfig config={stepConfig} onChange={onChange} />,
    condition: () => <ExpressionConfig label="Condition expression" configKey="expression" config={stepConfig} onChange={onChange} placeholder="output.score > 0.8" />,
    switch: () => <SwitchConfig config={stepConfig} onChange={onChange} />,
    transform: () => <TransformConfig config={stepConfig} onChange={onChange} />,
    code: () => <CodeConfig config={stepConfig} onChange={onChange} />,
    foreach: () => <ForEachConfig config={stepConfig} onChange={onChange} />,
    delay: () => <DelayConfig config={stepConfig} onChange={onChange} />,
    merge: () => <MergeConfig config={stepConfig} onChange={onChange} />,
    knowledge_search: () => <KnowledgeSearchConfig config={stepConfig} onChange={onChange} />,
  };

  const renderer = renderers[stepType];
  if (!renderer) return null;

  return (
    <div className="space-y-3 rounded-xl border border-[#e0e7ff] bg-[#f5f3ff]/50 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#6366f1]">
        Node configuration
      </p>
      {renderer()}
    </div>
  );
}

// ── Shared field helper ──────────────────────────────────────────────────────

function ConfigField({ label, value, onChange, placeholder, type = "text", rows }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string; rows?: number;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium text-[#475467]">{label}</span>
      {rows ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={rows}
          className="w-full resize-none rounded-lg border border-black/[0.12] bg-white px-2.5 py-1.5 font-mono text-[12px] text-[#101828] outline-none focus:border-[#818cf8]"
        />
      ) : (
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-lg border border-black/[0.12] bg-white px-2.5 py-1.5 text-[12px] text-[#101828] outline-none focus:border-[#818cf8]"
        />
      )}
    </label>
  );
}

// ── Per-type configs ─────────────────────────────────────────────────────────

function HttpRequestConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  const set = (k: string, v: unknown) => onChange({ ...config, [k]: v });
  return (
    <div className="space-y-2">
      <ConfigField label="URL" value={String(config.url || "")} onChange={(v) => set("url", v)} placeholder="https://api.example.com/{id}" />
      <label className="block">
        <span className="mb-1 block text-[11px] font-medium text-[#475467]">Method</span>
        <select
          value={String(config.method || "GET")}
          onChange={(e) => set("method", e.target.value)}
          className="w-full rounded-lg border border-black/[0.12] bg-white px-2.5 py-1.5 text-[12px] text-[#101828] outline-none focus:border-[#818cf8]"
        >
          {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => <option key={m}>{m}</option>)}
        </select>
      </label>
      <ConfigField label="Timeout (s)" value={String(config.timeout_s || "30")} onChange={(v) => set("timeout_s", Number(v) || 30)} type="number" />
    </div>
  );
}

function ExpressionConfig({ label, configKey, config, onChange, placeholder }: {
  label: string; configKey: string; config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void; placeholder?: string;
}) {
  return (
    <ConfigField
      label={label}
      value={String(config[configKey] || "")}
      onChange={(v) => onChange({ ...config, [configKey]: v })}
      placeholder={placeholder}
    />
  );
}

function SwitchConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  const set = (k: string, v: unknown) => onChange({ ...config, [k]: v });
  const [caseInput, setCaseInput] = useState("");
  const cases = (config.cases || {}) as Record<string, string>;
  return (
    <div className="space-y-2">
      <ConfigField label="Value key" value={String(config.value_key || "")} onChange={(v) => set("value_key", v)} placeholder="status" />
      <ConfigField label="Default label" value={String(config.default || "none")} onChange={(v) => set("default", v)} />
      <div>
        <span className="mb-1 block text-[11px] font-medium text-[#475467]">Cases (value=label)</span>
        <div className="space-y-1">
          {Object.entries(cases).map(([val, lbl]) => (
            <div key={val} className="flex items-center gap-1 text-[11px] text-[#475467]">
              <span className="font-mono">{val}</span> → <span>{lbl}</span>
              <button type="button" onClick={() => { const next = { ...cases }; delete next[val]; set("cases", next); }} className="ml-auto text-[#f04438] text-[10px]">×</button>
            </div>
          ))}
        </div>
        <div className="mt-1 flex gap-1">
          <input
            value={caseInput}
            onChange={(e) => setCaseInput(e.target.value)}
            placeholder="value=label"
            className="min-w-0 flex-1 rounded-lg border border-black/[0.12] bg-white px-2 py-1 text-[11px] outline-none"
          />
          <button type="button" onClick={() => {
            const [v, l] = caseInput.split("=");
            if (v && l) { set("cases", { ...cases, [v.trim()]: l.trim() }); setCaseInput(""); }
          }} className="rounded-lg bg-[#6366f1] px-2 py-1 text-[10px] font-semibold text-white">Add</button>
        </div>
      </div>
    </div>
  );
}

function TransformConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  const mapping = (config.mapping || {}) as Record<string, string>;
  const [entry, setEntry] = useState("");
  return (
    <div className="space-y-2">
      <span className="block text-[11px] font-medium text-[#475467]">Field mapping (out=input.key|transform)</span>
      <div className="space-y-1">
        {Object.entries(mapping).map(([k, v]) => (
          <div key={k} className="flex items-center gap-1 text-[11px] font-mono text-[#475467]">
            {k} = {v}
            <button type="button" onClick={() => { const next = { ...mapping }; delete next[k]; onChange({ ...config, mapping: next }); }} className="ml-auto text-[#f04438] text-[10px]">×</button>
          </div>
        ))}
      </div>
      <div className="flex gap-1">
        <input value={entry} onChange={(e) => setEntry(e.target.value)} placeholder="output_field=input.key" className="min-w-0 flex-1 rounded-lg border border-black/[0.12] bg-white px-2 py-1 font-mono text-[11px] outline-none" />
        <button type="button" onClick={() => {
          const [k, v] = entry.split("=");
          if (k && v) { onChange({ ...config, mapping: { ...mapping, [k.trim()]: v.trim() } }); setEntry(""); }
        }} className="rounded-lg bg-[#6366f1] px-2 py-1 text-[10px] font-semibold text-white">Add</button>
      </div>
    </div>
  );
}

function CodeConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <ConfigField
      label="Python expression"
      value={String(config.code || "")}
      onChange={(v) => onChange({ ...config, code: v })}
      placeholder="len(items) > 0"
      rows={3}
    />
  );
}

function ForEachConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  const set = (k: string, v: unknown) => onChange({ ...config, [k]: v });
  return (
    <div className="space-y-2">
      <ConfigField label="Items key" value={String(config.items_key || "items")} onChange={(v) => set("items_key", v)} placeholder="items" />
      <ConfigField label="Body step type" value={String(config.body_step_type || "transform")} onChange={(v) => set("body_step_type", v)} placeholder="transform" />
      <ConfigField label="Max items" value={String(config.max_items || "100")} onChange={(v) => set("max_items", Number(v) || 100)} type="number" />
    </div>
  );
}

function DelayConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <ConfigField
      label="Delay (seconds)"
      value={String(config.seconds || "1")}
      onChange={(v) => onChange({ ...config, seconds: Number(v) || 1 })}
      type="number"
    />
  );
}

function MergeConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <div className="space-y-2">
      <label className="block">
        <span className="mb-1 block text-[11px] font-medium text-[#475467]">Strategy</span>
        <select
          value={String(config.strategy || "dict")}
          onChange={(e) => onChange({ ...config, strategy: e.target.value })}
          className="w-full rounded-lg border border-black/[0.12] bg-white px-2.5 py-1.5 text-[12px] text-[#101828] outline-none focus:border-[#818cf8]"
        >
          <option value="dict">Dict merge</option>
          <option value="list">Collect as list</option>
          <option value="concat">Concatenate strings</option>
        </select>
      </label>
    </div>
  );
}

function KnowledgeSearchConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  const set = (k: string, v: unknown) => onChange({ ...config, [k]: v });
  const topK = Number(config.top_k || 5);
  const threshold = Number(config.score_threshold || 0);

  return (
    <div className="space-y-3">
      <div>
        <span className="mb-1 block text-[12px] font-semibold text-[#344054]">What to search for</span>
        <span className="mb-2 block text-[11px] text-[#667085]">
          Which input should be used as the search query? This is usually the question or topic from a previous step.
        </span>
        <ConfigField
          label="Query input key"
          value={String(config.query_key || "query")}
          onChange={(v) => set("query_key", v)}
          placeholder="query"
        />
      </div>

      <div>
        <span className="mb-1 block text-[12px] font-semibold text-[#344054]">How many results</span>
        <span className="mb-2 block text-[11px] text-[#667085]">
          More results give broader context but take longer to process.
        </span>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={1}
            max={20}
            value={topK}
            onChange={(e) => set("top_k", Number(e.target.value))}
            className="flex-1 accent-[#7c3aed]"
          />
          <span className="w-8 text-center text-[13px] font-semibold text-[#101828]">{topK}</span>
        </div>
      </div>

      <div>
        <span className="mb-1 block text-[12px] font-semibold text-[#344054]">Search method</span>
        <div className="flex gap-1.5">
          {([
            { value: "hybrid", label: "Smart", hint: "Combines keywords + meaning" },
            { value: "vector", label: "Meaning", hint: "Finds similar meaning" },
            { value: "text", label: "Keyword", hint: "Matches exact words" },
          ] as const).map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => set("retrieval_mode", opt.value)}
              className={`flex-1 rounded-lg border px-2 py-2 text-center transition-colors ${
                String(config.retrieval_mode || "hybrid") === opt.value
                  ? "border-[#7c3aed] bg-[#f5f3ff]"
                  : "border-black/[0.08] bg-white hover:bg-[#f8fafc]"
              }`}
            >
              <p className={`text-[12px] font-semibold ${String(config.retrieval_mode || "hybrid") === opt.value ? "text-[#7c3aed]" : "text-[#344054]"}`}>{opt.label}</p>
              <p className="mt-0.5 text-[10px] text-[#667085]">{opt.hint}</p>
            </button>
          ))}
        </div>
      </div>

      <div>
        <span className="mb-1 block text-[12px] font-semibold text-[#344054]">Minimum relevance</span>
        <span className="mb-2 block text-[11px] text-[#667085]">
          Only return results above this quality threshold. 0 returns everything.
        </span>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={Math.round(threshold * 100)}
            onChange={(e) => set("score_threshold", Number(e.target.value) / 100)}
            className="flex-1 accent-[#7c3aed]"
          />
          <span className="w-10 text-center text-[13px] font-semibold text-[#101828]">
            {threshold === 0 ? "Any" : `${Math.round(threshold * 100)}%`}
          </span>
        </div>
      </div>

      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={config.include_metadata !== false}
          onChange={(e) => set("include_metadata", e.target.checked)}
          className="rounded accent-[#7c3aed]"
        />
        <span className="text-[12px] text-[#344054]">Include source file names and page numbers</span>
      </label>
    </div>
  );
}

export { StepTypeConfig };
