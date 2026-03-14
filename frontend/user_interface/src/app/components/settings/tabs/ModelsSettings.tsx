import { useCallback, useEffect, useState } from "react";
import type {
  LlamaCppCatalogEntry,
  LlamaCppModelRecord,
  LlamaCppStatus,
  OllamaModelRecord,
  OllamaStatus,
} from "../../../../api/integrations";
import {
  downloadLlamaCppModel,
  getLlamaCppCatalog,
  getLlamaCppStatus,
  listLlamaCppModels,
  saveLlamaCppConfig,
  selectLlamaCppModel,
  startLlamaCppServer,
  stopLlamaCppServer,
} from "../../../../api/integrations";
import { SettingsRow } from "../ui/SettingsRow";
import { SettingsSection } from "../ui/SettingsSection";
import { StatusChip, toneFromBoolean } from "../ui/StatusChip";
import { ComputerUseSettings } from "./ComputerUseSettings";

type ModelsSettingsProps = {
  ollamaStatus: OllamaStatus;
  ollamaModels: OllamaModelRecord[];
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
    | "onboarding"
    | null;
  ollamaProgress: { status: string; percent: number } | null;
  ollamaMessage: string;
  setOllamaBaseUrlInput: (value: string) => void;
  setOllamaModelInput: (value: string) => void;
  setOllamaEmbeddingInput: (value: string) => void;
  onOneClickSetup: () => void;
  onSaveConfig: () => void;
  onStartOllama: () => void;
  onRefreshModels: () => void;
  onPullModel: (modelOverride?: string) => void;
  onSelectModel: (model: string) => void;
  onPullEmbeddingModel: (modelOverride?: string) => void;
  onSelectEmbeddingModel: (model: string) => void;
  onApplyEmbeddingToAllCollections: () => void;
  computerUseModelActive: string;
  computerUseModelSource: string;
  computerUseModelInput: string;
  computerUseModelSaved: string;
  computerUseModelSaving: boolean;
  onComputerUseModelInputChange: (value: string) => void;
  onSaveComputerUseModel: () => void;
  onClearComputerUseModel: () => void;
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

function formatGb(gb: number) {
  if (gb < 1) return `${Math.round(gb * 1024)} MB`;
  return `${gb.toFixed(1)} GB`;
}

function LlamaCppSection() {
  const [status, setStatus] = useState<LlamaCppStatus | null>(null);
  const [catalog, setCatalog] = useState<LlamaCppCatalogEntry[]>([]);
  const [localModels, setLocalModels] = useState<LlamaCppModelRecord[]>([]);
  const [portInput, setPortInput] = useState("8082");
  const [busyFilename, setBusyFilename] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [progress, setProgress] = useState<{ percent: number; filename: string } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([getLlamaCppStatus(), listLlamaCppModels()]);
      setStatus(s);
      setLocalModels(m.models);
      setPortInput(String(s.port ?? 8082));
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    getLlamaCppCatalog()
      .then((r) => setCatalog(r.models))
      .catch(() => {});
    refresh();
  }, [refresh]);

  const handleDownload = async (entry: LlamaCppCatalogEntry) => {
    setBusyFilename(entry.filename);
    setMessage(`Downloading ${entry.name}...`);
    setProgress({ percent: 0, filename: entry.filename });
    try {
      await downloadLlamaCppModel({ url: entry.url, filename: entry.filename });
      setMessage(`Downloaded: ${entry.filename}`);
      setProgress(null);
      await refresh();
    } catch {
      setMessage(`Download failed: ${entry.filename}`);
      setProgress(null);
    } finally {
      setBusyFilename(null);
    }
  };

  const handleStartAndUse = async (filename: string) => {
    setBusyFilename(filename);
    setMessage(`Starting server with ${filename}...`);
    try {
      const result = await startLlamaCppServer({
        modelFilename: filename,
        port: parseInt(portInput, 10) || 8082,
      });
      if (result.reachable) {
        setMessage(`Server running on port ${portInput}. Model active.`);
      } else {
        // Try selecting anyway (server may still be starting)
        await selectLlamaCppModel({ modelFilename: filename }).catch(() => {});
        setMessage(`Server starting — may take a moment. Refresh to check status.`);
      }
      await refresh();
    } catch {
      setMessage(`Failed to start server with ${filename}.`);
    } finally {
      setBusyFilename(null);
    }
  };

  const handleStop = async () => {
    setBusyFilename("__stop__");
    try {
      await stopLlamaCppServer();
      setMessage("Server stopped.");
      await refresh();
    } catch {
      setMessage("Failed to stop server.");
    } finally {
      setBusyFilename(null);
    }
  };

  const handleSavePort = async () => {
    const port = parseInt(portInput, 10);
    if (!port || port < 1024 || port > 65535) {
      setMessage("Port must be between 1024 and 65535.");
      return;
    }
    try {
      await saveLlamaCppConfig({ port });
      setMessage(`Port saved: ${port}`);
      await refresh();
    } catch {
      setMessage("Failed to save config.");
    }
  };

  const isBusy = busyFilename !== null;
  const isReachable = status?.reachable ?? false;
  const isInstalled = status?.installed ?? false;
  const runtimeChip = toneFromBoolean(isReachable, { trueLabel: "Running", falseLabel: isInstalled ? "Stopped" : "Not installed" });

  const chatCatalog = catalog.filter((e) => e.type === "chat");
  const embedCatalog = catalog.filter((e) => e.type === "embedding");

  return (
    <SettingsSection
      title="Local Models"
      subtitle="Download GGUF models from HuggingFace and serve them directly — no Ollama required."
      actions={<StatusChip label={runtimeChip.label} tone={runtimeChip.tone} />}
    >

      <SettingsRow
        title="Server port"
        description="Port the llama-cpp-python server listens on."
        right={
          <div className="flex items-center gap-2">
            {isReachable && (
              <button
                type="button"
                onClick={handleStop}
                disabled={isBusy}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#c00] hover:bg-[#f5f5f7] disabled:opacity-50"
              >
                Stop server
              </button>
            )}
            <button
              type="button"
              onClick={refresh}
              disabled={isBusy}
              className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-50"
            >
              Refresh
            </button>
            <button
              type="button"
              onClick={handleSavePort}
              disabled={isBusy}
              className="rounded-xl bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:opacity-50"
            >
              Save
            </button>
          </div>
        }
      >
        <input
          type="number"
          value={portInput}
          onChange={(e) => setPortInput(e.target.value)}
          aria-label="llama.cpp server port"
          disabled={isBusy}
          className="w-32 rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] focus:outline-none focus:border-[#8e8e93]"
        />
        {status?.active_model && (
          <p className="mt-1 text-[12px] text-[#6e6e73]">Active model: {status.active_model}</p>
        )}
      </SettingsRow>

      {chatCatalog.length > 0 && (
        <SettingsRow
          title="Chat models"
          description="Download a GGUF model from HuggingFace and start the server."
        >
          <div className="space-y-2">
            {chatCatalog.map((entry) => {
              const isDownloaded = localModels.some((m) => m.filename === entry.filename);
              const isActive = status?.active_model === entry.filename;
              const isBusyThis = busyFilename === entry.filename;
              return (
                <div
                  key={entry.filename}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#ececf0] bg-white px-4 py-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-[13px] font-semibold text-[#1d1d1f]">{entry.name}</p>
                      {entry.recommended && (
                        <span className="rounded-full bg-[#e8f5e9] px-2 py-0.5 text-[11px] font-medium text-[#2e7d32]">
                          Recommended
                        </span>
                      )}
                    </div>
                    <p className="text-[12px] text-[#6e6e73]">{formatGb(entry.size_gb)}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {!isDownloaded ? (
                      <button
                        type="button"
                        onClick={() => handleDownload(entry)}
                        disabled={isBusy}
                        className="rounded-xl bg-[#1d1d1f] px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:opacity-50"
                      >
                        {isBusyThis ? "Downloading..." : "Download"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleStartAndUse(entry.filename)}
                        disabled={isBusy || isActive}
                        className={`rounded-xl border px-3 py-1.5 text-[12px] font-semibold transition ${
                          isActive
                            ? "border-[#d2d2d7] bg-[#f5f5f7] text-[#6e6e73]"
                            : "border-[#d2d2d7] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
                        } disabled:opacity-50`}
                      >
                        {isActive ? "Active" : isBusyThis ? "Starting..." : "Start + Use"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </SettingsRow>
      )}

      {embedCatalog.length > 0 && (
        <SettingsRow
          title="Embedding models"
          description="Download a GGUF embedding model."
        >
          <div className="space-y-2">
            {embedCatalog.map((entry) => {
              const isDownloaded = localModels.some((m) => m.filename === entry.filename);
              const isActive = status?.active_embedding === entry.filename;
              const isBusyThis = busyFilename === entry.filename;
              return (
                <div
                  key={entry.filename}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#ececf0] bg-white px-4 py-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-[13px] font-semibold text-[#1d1d1f]">{entry.name}</p>
                      {entry.recommended && (
                        <span className="rounded-full bg-[#e8f5e9] px-2 py-0.5 text-[11px] font-medium text-[#2e7d32]">
                          Recommended
                        </span>
                      )}
                    </div>
                    <p className="text-[12px] text-[#6e6e73]">{formatGb(entry.size_gb)}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {!isDownloaded ? (
                      <button
                        type="button"
                        onClick={() => handleDownload(entry)}
                        disabled={isBusy}
                        className="rounded-xl bg-[#1d1d1f] px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:opacity-50"
                      >
                        {isBusyThis ? "Downloading..." : "Download"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => selectLlamaCppModel({ modelFilename: entry.filename }).then(refresh).catch(() => {})}
                        disabled={isBusy || isActive}
                        className={`rounded-xl border px-3 py-1.5 text-[12px] font-semibold transition ${
                          isActive
                            ? "border-[#d2d2d7] bg-[#f5f5f7] text-[#6e6e73]"
                            : "border-[#d2d2d7] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
                        } disabled:opacity-50`}
                      >
                        {isActive ? "Active" : "Use"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </SettingsRow>
      )}

      {progress && (
        <SettingsRow
          title="Download progress"
          description={`${progress.filename} — ${progress.percent.toFixed(1)}%`}
          right={<StatusChip label={`${progress.percent.toFixed(0)}%`} tone="neutral" />}
          noDivider
        >
          <div className="h-1.5 overflow-hidden rounded-full bg-[#ececf0]">
            <div
              className="h-full rounded-full bg-[#1d1d1f] transition-all"
              style={{ width: `${Math.max(0, Math.min(100, progress.percent))}%` }}
            />
          </div>
        </SettingsRow>
      )}

      {localModels.length > 0 && (
        <SettingsRow
          title="Downloaded models"
          description={`${localModels.length} GGUF file(s) on server disk.`}
          right={<StatusChip label={`${localModels.length} file(s)`} tone="neutral" />}
          noDivider
        >
          <div className="overflow-hidden rounded-xl border border-[#ececf0]">
            {localModels.map((model, index) => (
              <div
                key={model.filename}
                className={`flex flex-wrap items-center justify-between gap-3 bg-white px-4 py-3 ${index < localModels.length - 1 ? "border-b border-[#f2f2f4]" : ""}`}
              >
                <div>
                  <p className="text-[13px] font-semibold text-[#1d1d1f]">{model.filename}</p>
                  <p className="text-[12px] text-[#6e6e73]">{formatModelSize(model.size_bytes)}</p>
                </div>
              </div>
            ))}
          </div>
        </SettingsRow>
      )}

      {message ? (
        <div className="rounded-xl border border-[#ececf0] bg-white px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">{message}</p>
        </div>
      ) : null}
    </SettingsSection>
  );
}

export function ModelsSettings({
  ollamaStatus,
  ollamaModels,
  ollamaBaseUrlInput,
  ollamaModelInput,
  ollamaEmbeddingInput,
  ollamaBusyAction,
  ollamaProgress,
  ollamaMessage,
  setOllamaBaseUrlInput,
  setOllamaModelInput,
  setOllamaEmbeddingInput,
  onOneClickSetup,
  onSaveConfig,
  onStartOllama,
  onRefreshModels,
  onPullModel,
  onSelectModel,
  onPullEmbeddingModel,
  onSelectEmbeddingModel,
  onApplyEmbeddingToAllCollections,
  computerUseModelActive,
  computerUseModelSource,
  computerUseModelInput,
  computerUseModelSaved,
  computerUseModelSaving,
  onComputerUseModelInputChange,
  onSaveComputerUseModel,
  onClearComputerUseModel,
}: ModelsSettingsProps) {
  const runtimeChip = toneFromBoolean(ollamaStatus.reachable, { trueLabel: "Online", falseLabel: "Offline" });
  const isBusy = ollamaBusyAction !== null;
  const isOnboarding = ollamaBusyAction === "onboarding";

  return (
    <>
      <LlamaCppSection />

      <SettingsSection
        title="Ollama"
        subtitle="Use Ollama if it is already installed on this server."
        actions={<StatusChip label={runtimeChip.label} tone={runtimeChip.tone} />}
      >
        <SettingsRow
          title="One-click start chat"
          description="Best for non-technical users. Starts Ollama, downloads recommended chat + embedding models, and activates them."
          right={
            <button
              type="button"
              onClick={onOneClickSetup}
              disabled={isBusy}
              className="rounded-xl bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:opacity-50"
            >
              {isOnboarding ? "Setting up..." : "One-click setup"}
            </button>
          }
        />

        <SettingsRow
          title="Ollama host URL"
          description="Local endpoint where Maia discovers installed models."
          right={
            <>
              <button
                type="button"
                onClick={onSaveConfig}
                disabled={isBusy}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-50"
              >
                Save URL
              </button>
              <button
                type="button"
                onClick={onRefreshModels}
                disabled={isBusy}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-50"
              >
                Refresh models
              </button>
              <button
                type="button"
                onClick={onStartOllama}
                disabled={isBusy}
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
            disabled={isBusy}
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
              disabled={isBusy}
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
              disabled={isBusy}
              className="w-full rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#a1a1a6] focus:outline-none focus:border-[#8e8e93]"
              placeholder="qwen3:8b"
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
                  disabled={isBusy}
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
                      disabled={isBusy || isActive}
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
                disabled={isBusy}
                className="rounded-xl bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:opacity-50"
              >
                Download & Use
              </button>
              <button
                type="button"
                onClick={() => onSelectEmbeddingModel(ollamaEmbeddingInput)}
                disabled={isBusy}
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
              disabled={isBusy}
              className="w-full rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#a1a1a6] focus:outline-none focus:border-[#8e8e93]"
              placeholder="embeddinggemma"
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
                  disabled={isBusy}
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
              disabled={isBusy}
              className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:opacity-50"
            >
              Apply to all + Reindex
            </button>
          }
          noDivider
        />
      </SettingsSection>

      <ComputerUseSettings
        activeModel={computerUseModelActive}
        activeModelSource={computerUseModelSource}
        overrideModelInput={computerUseModelInput}
        savedOverrideModel={computerUseModelSaved}
        isSaving={computerUseModelSaving}
        onOverrideModelInputChange={onComputerUseModelInputChange}
        onSaveOverrideModel={onSaveComputerUseModel}
        onClearOverrideModel={onClearComputerUseModel}
      />

      {ollamaMessage ? (
        <div className="rounded-xl border border-[#ececf0] bg-white px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">{ollamaMessage}</p>
        </div>
      ) : null}
    </>
  );
}
