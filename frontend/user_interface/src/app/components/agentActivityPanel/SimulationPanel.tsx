import { useState } from "react";
import {
  FlaskConical,
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  Wrench,
  MessageSquare,
} from "lucide-react";

type SimStep = {
  step_index: number;
  event_type: string;
  ts: number;
  tool_id?: string;
  text?: string;
  mock_response?: unknown;
  error?: string;
  [key: string]: unknown;
};

type SimResult = {
  run_id: string;
  agent_id: string;
  scenario_input: string;
  steps: SimStep[];
  completed: boolean;
  error: string | null;
  duration_ms: number;
};

type SimulationPanelProps = {
  agentId: string;
};

function StepRow({ step }: { step: SimStep }) {
  const [open, setOpen] = useState(false);

  const isToolCall = step.event_type.startsWith("tool");
  const isError = step.event_type.includes("error");
  const isComplete = step.event_type.includes("complete");

  return (
    <div className="border-b border-border/20 last:border-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-accent/20 transition-colors"
      >
        <span className="text-muted-foreground/50 text-[10px] w-5 shrink-0 text-right">
          {step.step_index + 1}
        </span>
        {isToolCall ? (
          <Wrench size={11} className="text-yellow-400 shrink-0" />
        ) : isError ? (
          <XCircle size={11} className="text-destructive shrink-0" />
        ) : isComplete ? (
          <CheckCircle2 size={11} className="text-green-400 shrink-0" />
        ) : (
          <MessageSquare size={11} className="text-violet-400 shrink-0" />
        )}
        <span className="flex-1 text-xs text-foreground truncate">
          {step.tool_id
            ? `Tool: ${step.tool_id}${step.mock_response !== undefined ? " (mocked)" : ""}`
            : step.text
            ? step.text.slice(0, 60) + (step.text.length > 60 ? "…" : "")
            : step.event_type}
        </span>
        {open ? (
          <ChevronDown size={11} className="text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight size={11} className="text-muted-foreground shrink-0" />
        )}
      </button>
      {open && (
        <div className="px-4 pb-3 pt-1">
          <pre className="text-[10px] text-muted-foreground bg-muted/30 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">
            {JSON.stringify(step, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

export function SimulationPanel({ agentId }: SimulationPanelProps) {
  const [input, setInput] = useState("");
  const [mockedToolsRaw, setMockedToolsRaw] = useState("{}");
  const [result, setResult] = useState<SimResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setError(null);
    setResult(null);
    setRunning(true);
    try {
      let mocked_tools: Record<string, unknown> = {};
      try {
        mocked_tools = JSON.parse(mockedToolsRaw) as Record<string, unknown>;
      } catch {
        setError("Mocked tools must be valid JSON.");
        return;
      }
      const res = await fetch(`/api/agents/${agentId}/simulate`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: input || "Simulate agent run.", mocked_tools }),
      });
      if (!res.ok) {
        const e = await res.json() as { detail?: string };
        throw new Error(e.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json() as SimResult;
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Config panel */}
      <div className="px-4 pt-4 pb-3 border-b border-border/50 space-y-3">
        <div className="flex items-center gap-2 mb-1">
          <FlaskConical size={14} className="text-muted-foreground" />
          <span className="text-sm font-medium">Test Run</span>
        </div>

        <div>
          <label className="block text-xs text-muted-foreground mb-1">Input message</label>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={2}
            placeholder="Describe the task to simulate…"
            className="w-full text-xs bg-background border border-border/60 rounded px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>

        <div>
          <label className="block text-xs text-muted-foreground mb-1">
            Mocked tool responses (JSON)
          </label>
          <textarea
            value={mockedToolsRaw}
            onChange={(e) => setMockedToolsRaw(e.target.value)}
            rows={3}
            spellCheck={false}
            placeholder={'{"crm.get_pipeline": {"deals": [], "total": 0}}'}
            className="w-full font-mono text-[11px] bg-muted/20 border border-border/60 rounded px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <button
          onClick={() => void handleRun()}
          disabled={running}
          className="w-full flex items-center justify-center gap-2 py-2 rounded bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-40 transition-colors"
        >
          {running ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Play size={12} />
          )}
          Run Simulation
        </button>
      </div>

      {/* Results */}
      {result && (
        <div className="flex-1 overflow-y-auto">
          {/* Summary bar */}
          <div
            className={`px-4 py-2 flex items-center gap-2 text-xs border-b border-border/30 ${
              result.completed ? "bg-green-500/5" : "bg-destructive/5"
            }`}
          >
            {result.completed ? (
              <CheckCircle2 size={12} className="text-green-400" />
            ) : (
              <XCircle size={12} className="text-destructive" />
            )}
            <span>
              {result.completed ? "Completed" : "Failed"} · {result.steps.length} steps ·{" "}
              {result.duration_ms}ms
            </span>
            <span className="ml-auto font-mono text-muted-foreground/50 text-[10px]">
              {result.run_id}
            </span>
          </div>

          {/* Step list */}
          {result.steps.map((step) => (
            <StepRow key={step.step_index} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}
