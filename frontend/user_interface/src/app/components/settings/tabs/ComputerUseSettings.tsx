import { SettingsRow } from "../ui/SettingsRow";
import { SettingsSection } from "../ui/SettingsSection";
import { StatusChip } from "../ui/StatusChip";

type ComputerUseSettingsProps = {
  activeModel: string;
  activeModelSource: string;
  overrideModelInput: string;
  savedOverrideModel: string;
  isSaving: boolean;
  onOverrideModelInputChange: (value: string) => void;
  onSaveOverrideModel: () => void;
  onClearOverrideModel: () => void;
};

function resolveProvider(modelName: string) {
  const normalized = String(modelName || "").trim().toLowerCase();
  if (!normalized) {
    return "Not configured";
  }
  if (normalized.startsWith("claude")) {
    return "Anthropic";
  }
  if (
    normalized.startsWith("gpt") ||
    normalized.startsWith("o1") ||
    normalized.startsWith("o3") ||
    normalized.startsWith("o4")
  ) {
    return "OpenAI";
  }
  if (
    normalized.includes(":") ||
    normalized.startsWith("qwen") ||
    normalized.startsWith("llama") ||
    normalized.startsWith("mistral") ||
    normalized.startsWith("gemma") ||
    normalized.startsWith("deepseek")
  ) {
    return "Ollama";
  }
  return "Not configured";
}

function normalizeSource(source: string) {
  const normalized = String(source || "").trim().toLowerCase();
  if (!normalized) {
    return "Unknown source";
  }
  if (normalized.includes("agent.computer_use_model")) {
    return "Saved override";
  }
  if (normalized.includes("computer_use_model")) {
    return "COMPUTER_USE_MODEL";
  }
  if (normalized.includes("openai_chat_model")) {
    return "OPENAI_CHAT_MODEL";
  }
  if (normalized.includes("fallback") || normalized.includes("default")) {
    return "Fallback (gpt-4o)";
  }
  return source;
}

export function ComputerUseSettings({
  activeModel,
  activeModelSource,
  overrideModelInput,
  savedOverrideModel,
  isSaving,
  onOverrideModelInputChange,
  onSaveOverrideModel,
  onClearOverrideModel,
}: ComputerUseSettingsProps) {
  const effectiveModel = String(activeModel || "").trim();
  const provider = resolveProvider(effectiveModel);
  const sourceLabel = normalizeSource(activeModelSource);
  const overrideSaved = String(savedOverrideModel || "").trim();

  return (
    <SettingsSection
      title="Computer Use Model"
      subtitle="Configure the model used by browser automation sessions."
      actions={<StatusChip label={provider} tone={provider === "Not configured" ? "neutral" : "success"} />}
    >
      <SettingsRow
        title="Active model"
        description="Resolution order: saved override -> COMPUTER_USE_MODEL -> OPENAI_CHAT_MODEL -> gpt-4o."
        right={<StatusChip label={sourceLabel} tone="neutral" />}
      >
        <div className="rounded-xl border border-[#ececf0] bg-white px-3 py-2">
          <p className="text-[13px] font-semibold text-[#1d1d1f]">
            {effectiveModel || "gpt-4o"}
          </p>
        </div>
      </SettingsRow>

      <SettingsRow
        title="Override model"
        description="When set, this override is stored per user and used before environment variables."
        right={
          <>
            <button
              type="button"
              onClick={onSaveOverrideModel}
              disabled={isSaving}
              className="rounded-xl bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:opacity-50"
            >
              {isSaving ? "Saving..." : "Save"}
            </button>
            <button
              type="button"
              onClick={onClearOverrideModel}
              disabled={isSaving || (!overrideModelInput.trim() && !overrideSaved)}
              className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-50"
            >
              Clear
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <input
            type="text"
            value={overrideModelInput}
            onChange={(event) => onOverrideModelInputChange(event.target.value)}
            aria-label="Computer use model override"
            disabled={isSaving}
            className="w-full rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#a1a1a6] focus:outline-none focus:border-[#8e8e93]"
            placeholder="qwen2-vl:7b"
            autoComplete="off"
          />
          <div className="flex flex-wrap gap-2">
            {["qwen2-vl:7b", "gpt-4o", "claude-opus-4-6"].map((modelName) => (
              <button
                key={modelName}
                type="button"
                onClick={() => onOverrideModelInputChange(modelName)}
                disabled={isSaving}
                className="rounded-full border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-medium text-[#3a3a3c] hover:bg-[#f5f5f7] disabled:opacity-50"
              >
                {modelName}
              </button>
            ))}
          </div>
        </div>
      </SettingsRow>
    </SettingsSection>
  );
}
