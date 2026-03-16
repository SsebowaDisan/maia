import { useState } from "react";
import { Wand2, CheckCircle2, XCircle, Save, Loader2 } from "lucide-react";

type ValidationResult = {
  valid: boolean;
  errors: string[];
};

type WorkflowBuilderTabProps = {
  onSave?: (name: string, definition: object) => void;
};

export function WorkflowBuilderTab({ onSave }: WorkflowBuilderTabProps) {
  const [description, setDescription] = useState("");
  const [maxSteps, setMaxSteps] = useState(6);
  const [yaml, setYaml] = useState("");
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedName, setSavedName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    if (!description.trim()) return;
    setGenerating(true);
    setError(null);
    setValidation(null);
    try {
      const res = await fetch("/api/workflows/generate", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description, max_steps: maxSteps }),
      });
      if (!res.ok) {
        const err = await res.json() as { detail?: string };
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json() as { definition: object };
      setYaml(JSON.stringify(data.definition, null, 2));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const handleValidate = async () => {
    if (!yaml.trim()) return;
    setValidating(true);
    try {
      let definition: object;
      try {
        definition = JSON.parse(yaml) as object;
      } catch {
        setValidation({ valid: false, errors: ["Invalid JSON — check syntax."] });
        return;
      }
      const res = await fetch("/api/workflows/validate", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ definition }),
      });
      const result = await res.json() as ValidationResult;
      setValidation(result);
    } finally {
      setValidating(false);
    }
  };

  const handleSave = async () => {
    if (!yaml.trim() || !savedName.trim()) return;
    let definition: object;
    try {
      definition = JSON.parse(yaml) as object;
    } catch {
      setValidation({ valid: false, errors: ["Cannot save — fix JSON syntax first."] });
      return;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/workflows", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: savedName, description, definition }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      onSave?.(savedName, definition);
      setSavedName("");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Description input */}
      <div className="px-4 pt-4 pb-3 border-b border-border/50 space-y-3">
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">
            Describe your automation
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Every Monday morning, pull last week's sales from CRM, compare against targets, and send a summary email to the team"
            rows={3}
            className="w-full text-sm bg-background border border-border/60 rounded-md px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-primary/50 placeholder:text-muted-foreground/40"
          />
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs text-muted-foreground whitespace-nowrap">Max steps:</label>
          <input
            type="number"
            min={1}
            max={20}
            value={maxSteps}
            onChange={(e) => setMaxSteps(Number(e.target.value))}
            className="w-16 text-sm bg-background border border-border/60 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
          <button
            onClick={() => void handleGenerate()}
            disabled={generating || !description.trim()}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-40 transition-colors"
          >
            {generating ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Wand2 size={12} />
            )}
            Generate
          </button>
        </div>
        {error && (
          <p className="text-xs text-destructive">{error}</p>
        )}
      </div>

      {/* JSON editor */}
      <div className="flex-1 flex flex-col min-h-0 px-4 py-3 gap-2">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-muted-foreground">
            Workflow definition (JSON)
          </label>
          <button
            onClick={() => void handleValidate()}
            disabled={validating || !yaml.trim()}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-40 transition-colors"
          >
            {validating ? <Loader2 size={11} className="animate-spin" /> : null}
            Validate
          </button>
        </div>

        <textarea
          value={yaml}
          onChange={(e) => {
            setYaml(e.target.value);
            setValidation(null);
          }}
          spellCheck={false}
          className="flex-1 font-mono text-xs bg-muted/30 border border-border/50 rounded-md p-3 resize-none focus:outline-none focus:ring-1 focus:ring-primary/50 min-h-0"
          placeholder='{"name": "...", "steps": [...]}'
        />

        {/* Validation result */}
        {validation && (
          <div
            className={`rounded-md px-3 py-2 text-xs flex items-start gap-2 ${
              validation.valid
                ? "bg-green-500/10 text-green-600 border border-green-500/20"
                : "bg-destructive/10 text-destructive border border-destructive/20"
            }`}
          >
            {validation.valid ? (
              <CheckCircle2 size={13} className="shrink-0 mt-0.5" />
            ) : (
              <XCircle size={13} className="shrink-0 mt-0.5" />
            )}
            <div>
              {validation.valid ? (
                <span>Workflow is valid</span>
              ) : (
                <ul className="space-y-0.5">
                  {validation.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Save bar */}
      {yaml.trim() && (
        <div className="px-4 py-3 border-t border-border/50 flex items-center gap-2">
          <input
            type="text"
            value={savedName}
            onChange={(e) => setSavedName(e.target.value)}
            placeholder="Workflow name…"
            className="flex-1 text-sm bg-background border border-border/60 rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
          <button
            onClick={() => void handleSave()}
            disabled={saving || !savedName.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-40 transition-colors"
          >
            {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
            Save
          </button>
        </div>
      )}
    </div>
  );
}
