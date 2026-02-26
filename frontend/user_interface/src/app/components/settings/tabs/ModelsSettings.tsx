import type { OllamaModelRecord, OllamaQuickstart, OllamaStatus } from "../../../../api/integrations";
import { SettingsRow } from "../ui/SettingsRow";
import { SettingsSection } from "../ui/SettingsSection";
import { StatusChip, toneFromBoolean } from "../ui/StatusChip";

type ModelsSettingsProps = {
  ollamaStatus: OllamaStatus;
  ollamaModels: OllamaModelRecord[];
  ollamaQuickstart: OllamaQuickstart | null;
  ollamaBaseUrlInput: string;
  ollamaModelInput: string;
  ollamaEmbeddingInput: string;
  ollamaBusyAction:
    | "config"
    | "start"
    | "pull"
    | "select"
    | "select_embedding"
    | "apply_all"
    | "refresh"
    | null;
  ollamaProgress: { status: string; percent: number } | null;
  ollamaMessage: string;
  setOllamaBaseUrlInput: (value: string) => void;
  setOllamaModelInput: (value: string) => void;
  setOllamaEmbeddingInput: (value: string) => void;
  onSaveConfig: () => void;
  onStartOllama: () => void;
  onRefreshModels: () => void;
  onPullModel: (modelOverride?: string) => void;
  onSelectModel: (model: string) => void;
  onPullEmbeddingModel: (modelOverride?: string) => void;
  onSelectEmbeddingModel: (model: string) => void;
  onApplyEmbeddingToAllCollections: () => void;
};

function formatModelSize(sizeBytes: number) {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return "-";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = sizeBytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const digits = value >= 100 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits)} ${units[unitIndex]}`;
}

export function ModelsSettings({
  ollamaStatus,
  ollamaModels,
  ollamaQuickstart,
  ollamaBaseUrlInput,
  ollamaModelInput,
  ollamaEmbeddingInput,
  ollamaBusyAction,
  ollamaProgress,
  ollamaMessage,
  setOllamaBaseUrlInput,
  setOllamaModelInput,
  setOllamaEmbeddingInput,
  onSaveConfig,
  onStartOllama,
  onRefreshModels,
  onPullModel,
  onSelectModel,
  onPullEmbeddingModel,
  onSelectEmbeddingModel,
  onApplyEmbeddingToAllCollections,
}: ModelsSettingsProps) {
  const runtimeChip = toneFromBoolean(ollamaStatus.reachable, { trueLabel: "Online", falseLabel: "Offline" });

  return (
    <>
      <SettingsSection
        title="Local Models"
        subtitle="Run models privately on your machine."
        actions={<StatusChip label={runtimeChip.label} tone={runtimeChip.tone} />}
      >
        <SettingsRow
          title="Ollama host URL"
          description="Local endpoint where Maia discovers installed models."
          right={
            <>
              <button
                type="button"
                onClick={onSaveConfig}
                disabled={ollamaBusyAction === "config"}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-50"
              >
                Save URL
              </button>
              <button
                type="button"
                onClick={onRefreshModels}
                disabled={ollamaBusyAction === "refresh"}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-50"
              >
                Refresh models
              </button>
              <button
                type="button"
                onClick={onStartOllama}
                disabled={ollamaBusyAction === "start"}
                className="rounded-xl bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:opacity-50"
              >
                Start
              </button>
            </>
          }
        >
          <input
            type="text"
            value={ollamaBaseUrlInput}
            onChange={(event) => setOllamaBaseUrlInput(event.target.value)}
            aria-label="Ollama host URL"
            className="w-full rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#a1a1a6] focus:outline-none focus:border-[#8e8e93]"
            placeholder="http://127.0.0.1:11434"
            autoComplete="off"
          />
        </SettingsRow>

        <SettingsRow
          title="Download model"
          description="Pull a model from Ollama and activate it for chat."
          right={
            <button
              type="button"
              onClick={() => onPullModel()}
              disabled={ollamaBusyAction === "pull"}
              className="rounded-xl bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:opacity-50"
            >
              Download & Use
            </button>
          }
        >
          <div className="space-y-3">
            <input
              type="text"
              value={ollamaModelInput}
              onChange={(event) => setOllamaModelInput(event.target.value)}
              aria-label="Ollama model name"
              className="w-full rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#a1a1a6] focus:outline-none focus:border-[#8e8e93]"
              placeholder="llama3.2:3b"
              autoComplete="off"
            />
            <div className="flex flex-wrap gap-2">
              {(ollamaStatus.recommended_models || []).map((modelName) => (
                <button
                  key={modelName}
                  type="button"
                  onClick={() => {
                    setOllamaModelInput(modelName);
                    onPullModel(modelName);
                  }}
                  disabled={ollamaBusyAction === "pull"}
                  className="rounded-full border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-medium text-[#3a3a3c] hover:bg-[#f5f5f7] disabled:opacity-50"
                >
                  {modelName}
                </button>
              ))}
            </div>
          </div>
        </SettingsRow>

        {ollamaProgress ? (
          <SettingsRow
            title="Download progress"
            description={ollamaProgress.status}
            right={<StatusChip label={`${ollamaProgress.percent.toFixed(1)}%`} tone="neutral" />}
          >
            <div className="h-1.5 overflow-hidden rounded-full bg-[#ececf0]">
              <div
                className="h-full rounded-full bg-[#1d1d1f] transition-all"
                style={{ width: `${Math.max(0, Math.min(100, ollamaProgress.percent))}%` }}
              />
            </div>
          </SettingsRow>
        ) : null}

        <SettingsRow
          title="Installed models"
          description="Available local models detected from Ollama."
          right={<StatusChip label={`${ollamaModels.length} model(s)`} tone="neutral" />}
          noDivider
        >
          {ollamaModels.length === 0 ? (
            <p className="text-[12px] text-[#8e8e93]">No local Ollama models detected.</p>
          ) : (
            <div className="overflow-hidden rounded-xl border border-[#ececf0]">
              {ollamaModels.map((model, index) => {
                const isActive = model.name === ollamaStatus.active_model;
                return (
                  <div
                    key={model.name}
                    className={`flex flex-wrap items-center justify-between gap-3 bg-white px-4 py-3 ${index < ollamaModels.length - 1 ? "border-b border-[#f2f2f4]" : ""}`}
                  >
                    <div>
                      <p className="text-[13px] font-semibold text-[#1d1d1f]">{model.name}</p>
                      <p className="text-[12px] text-[#6e6e73]">{formatModelSize(model.size)}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => onSelectModel(model.name)}
                      disabled={ollamaBusyAction === "select" || isActive}
                      className={`rounded-xl border px-3 py-1.5 text-[12px] font-semibold transition ${
                        isActive
                          ? "border-[#d2d2d7] bg-[#f5f5f7] text-[#6e6e73]"
                          : "border-[#d2d2d7] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
                      } disabled:opacity-50`}
                    >
                      {isActive ? "Active" : "Use model"}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Embeddings"
        subtitle="Control indexing embeddings used for file collections."
      >
        <SettingsRow
          title="Embedding model for indexing"
          description="Select and activate the local embedding model used for future indexing."
          right={
            <>
              <button
                type="button"
                onClick={() => onPullEmbeddingModel()}
                disabled={ollamaBusyAction === "pull" || ollamaBusyAction === "select_embedding"}
                className="rounded-xl bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:opacity-50"
              >
                Download & Use
              </button>
              <button
                type="button"
                onClick={() => onSelectEmbeddingModel(ollamaEmbeddingInput)}
                disabled={ollamaBusyAction === "select_embedding"}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-50"
              >
                Use existing
              </button>
            </>
          }
        >
          <div className="space-y-3">
            <input
              type="text"
              value={ollamaEmbeddingInput}
              onChange={(event) => setOllamaEmbeddingInput(event.target.value)}
              aria-label="Ollama embedding model name"
              className="w-full rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#a1a1a6] focus:outline-none focus:border-[#8e8e93]"
              placeholder="nomic-embed-text"
              autoComplete="off"
            />
            <div className="flex flex-wrap gap-2">
              {(ollamaStatus.recommended_embedding_models || []).map((modelName) => (
                <button
                  key={modelName}
                  type="button"
                  onClick={() => {
                    setOllamaEmbeddingInput(modelName);
                    onPullEmbeddingModel(modelName);
                  }}
                  disabled={ollamaBusyAction === "pull" || ollamaBusyAction === "select_embedding"}
                  className="rounded-full border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-medium text-[#3a3a3c] hover:bg-[#f5f5f7] disabled:opacity-50"
                >
                  {modelName}
                </button>
              ))}
            </div>
          </div>
        </SettingsRow>

        <SettingsRow
          title="Migration"
          description="Apply the selected embedding to all collections and queue full reindex jobs."
          right={
            <button
              type="button"
              onClick={onApplyEmbeddingToAllCollections}
              disabled={ollamaBusyAction === "apply_all" || ollamaBusyAction === "pull"}
              className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-50"
            >
              Apply to all + Reindex
            </button>
          }
          noDivider
        />
      </SettingsSection>

      {ollamaQuickstart ? (
        <SettingsSection title="Local setup" subtitle="Quick shell commands to bootstrap Ollama locally.">
          <SettingsRow
            title="Install"
            description={ollamaQuickstart.install_url}
            right={<StatusChip label="Quickstart" tone="neutral" />}
          />
          <SettingsRow
            title="Check CLI"
            description={ollamaQuickstart.commands.check}
            right={<StatusChip label="Step 2" tone="neutral" />}
          />
          <SettingsRow
            title="Start server"
            description={ollamaQuickstart.commands.start}
            right={<StatusChip label="Step 3" tone="neutral" />}
            noDivider
          />
        </SettingsSection>
      ) : null}

      {ollamaMessage ? (
        <div className="rounded-xl border border-[#ececf0] bg-white px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">{ollamaMessage}</p>
        </div>
      ) : null}
    </>
  );
}
