import { useState } from "react";

import type { AgentLiveEvent } from "../../../api/client";
import {
  applyOllamaEmbeddingToAllCollections,
  getOllamaIntegrationStatus,
  getOllamaQuickstart,
  listOllamaModels,
  pullOllamaModel,
  saveOllamaIntegrationConfig,
  selectOllamaEmbeddingModel,
  selectOllamaModel,
  startLocalOllama,
  type OllamaModelRecord,
  type OllamaQuickstart,
  type OllamaStatus,
} from "../../../api/integrations";

type RefreshFn = () => Promise<void>;

export function useOllamaSettings() {
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus>({
    configured: false,
    reachable: false,
    base_url: "http://127.0.0.1:11434",
    version: null,
    active_model: null,
    active_embedding_model: null,
    models: [],
    recommended_models: [],
    recommended_embedding_models: [],
  });
  const [ollamaModels, setOllamaModels] = useState<OllamaModelRecord[]>([]);
  const [ollamaQuickstart, setOllamaQuickstart] = useState<OllamaQuickstart | null>(null);
  const [ollamaBaseUrlInput, setOllamaBaseUrlInput] = useState("http://127.0.0.1:11434");
  const [ollamaModelInput, setOllamaModelInput] = useState("");
  const [ollamaEmbeddingInput, setOllamaEmbeddingInput] = useState("nomic-embed-text");
  const [ollamaBusyAction, setOllamaBusyAction] = useState<
    "config" | "start" | "pull" | "select" | "select_embedding" | "apply_all" | "refresh" | null
  >(null);
  const [ollamaProgress, setOllamaProgress] = useState<{ status: string; percent: number } | null>(null);
  const [ollamaMessage, setOllamaMessage] = useState("");

  const syncFromStatus = (statusRow: OllamaStatus, quickstartRow: OllamaQuickstart | null) => {
    setOllamaStatus(statusRow);
    setOllamaModels(statusRow.models || []);
    setOllamaBaseUrlInput(statusRow.base_url || "http://127.0.0.1:11434");
    setOllamaQuickstart(quickstartRow);
    setOllamaEmbeddingInput(
      (statusRow.active_embedding_model || statusRow.recommended_embedding_models?.[0] || "nomic-embed-text")
        .toString()
        .trim(),
    );
  };

  const handleLiveEvent = (event: AgentLiveEvent, onRefreshIntegrations: RefreshFn) => {
    if (event.type === "ollama.pull.progress") {
      const percentValue = Number(event.data?.percent ?? 0);
      const statusValue = String(event.data?.status || event.message || "downloading");
      setOllamaProgress({
        percent: Number.isFinite(percentValue) ? Math.max(0, Math.min(100, percentValue)) : 0,
        status: statusValue,
      });
    }
    if (event.type === "ollama.pull.completed") {
      setOllamaBusyAction(null);
      setOllamaProgress({ status: "success", percent: 100 });
      void onRefreshIntegrations();
    }
    if (
      event.type === "ollama.pull.failed" ||
      event.type === "ollama.start.failed" ||
      event.type === "ollama.embedding.apply_all.failed"
    ) {
      setOllamaBusyAction(null);
    }
    if (event.type === "ollama.start.completed" || event.type === "ollama.embedding.apply_all.completed") {
      setOllamaBusyAction(null);
      void onRefreshIntegrations();
    }
  };

  const handleSaveOllamaConfig = async () => {
    const baseUrl = ollamaBaseUrlInput.trim();
    if (!baseUrl) {
      setOllamaMessage("Ollama base URL is required.");
      return;
    }
    setOllamaBusyAction("config");
    try {
      await saveOllamaIntegrationConfig(baseUrl);
      const [statusRow, modelsRow] = await Promise.all([getOllamaIntegrationStatus(), listOllamaModels(baseUrl)]);
      setOllamaStatus(statusRow);
      setOllamaModels(modelsRow.models || []);
      setOllamaBaseUrlInput(statusRow.base_url || baseUrl);
      setOllamaMessage("Ollama base URL saved.");
    } catch (error) {
      setOllamaMessage(`Failed to save Ollama base URL: ${String(error)}`);
    } finally {
      setOllamaBusyAction(null);
    }
  };

  const handleStartOllamaLocally = async () => {
    const baseUrl = ollamaBaseUrlInput.trim() || undefined;
    setOllamaBusyAction("start");
    setOllamaMessage("Starting local Ollama...");
    try {
      const result = await startLocalOllama({ baseUrl, waitSeconds: 10 });
      const quickstart = await getOllamaQuickstart(baseUrl);
      setOllamaQuickstart(quickstart);
      setOllamaMessage(result.reachable ? "Ollama started." : "Startup command sent. Ollama may still be initializing.");
      if (result.status === "already_running") {
        setOllamaMessage("Ollama is already running.");
      }
      await handleRefreshOllamaModels();
    } catch (error) {
      setOllamaMessage(`Failed to start Ollama: ${String(error)}`);
    } finally {
      setOllamaBusyAction(null);
    }
  };

  const handleRefreshOllamaModels = async () => {
    const baseUrl = ollamaBaseUrlInput.trim();
    setOllamaBusyAction("refresh");
    try {
      const [statusRow, modelsRow] = await Promise.all([
        getOllamaIntegrationStatus(),
        listOllamaModels(baseUrl || undefined),
      ]);
      setOllamaStatus(statusRow);
      setOllamaModels(modelsRow.models || []);
      setOllamaBaseUrlInput(statusRow.base_url || baseUrl || "http://127.0.0.1:11434");
      setOllamaMessage(`Loaded ${modelsRow.models.length} local model(s).`);
    } catch (error) {
      setOllamaMessage(`Failed to refresh models: ${String(error)}`);
    } finally {
      setOllamaBusyAction(null);
    }
  };

  const handlePullOllamaModel = async (modelOverride?: string) => {
    const model = (modelOverride || ollamaModelInput).trim();
    const baseUrl = ollamaBaseUrlInput.trim() || undefined;
    if (!model) {
      setOllamaMessage("Enter an Ollama model, for example `llama3.2:3b`.");
      return;
    }
    setOllamaBusyAction("pull");
    setOllamaProgress({ status: "starting", percent: 0 });
    setOllamaMessage(`Downloading ${model}...`);
    try {
      const result = await pullOllamaModel({ model, baseUrl, autoSelect: true });
      setOllamaModels(result.models || []);
      setOllamaStatus((previous) => ({
        ...previous,
        configured: true,
        reachable: true,
        base_url: result.base_url || previous.base_url,
        active_model: result.active_model || model,
        models: result.models || [],
      }));
      setOllamaProgress({
        status: result.pull.status || "success",
        percent: Number(result.pull.percent || 100),
      });
      setOllamaMessage(`Model ${model} downloaded and activated.`);
      setOllamaModelInput(model);
    } catch (error) {
      setOllamaMessage(`Failed to download ${model}: ${String(error)}`);
    } finally {
      setOllamaBusyAction(null);
    }
  };

  const handleSelectOllamaModel = async (model: string) => {
    const cleanModel = model.trim();
    if (!cleanModel) {
      return;
    }
    setOllamaBusyAction("select");
    try {
      const result = await selectOllamaModel({
        model: cleanModel,
        baseUrl: ollamaBaseUrlInput.trim() || undefined,
      });
      setOllamaStatus((previous) => ({ ...previous, active_model: result.model }));
      setOllamaMessage(`Model ${cleanModel} is now active.`);
      await handleRefreshOllamaModels();
    } catch (error) {
      setOllamaMessage(`Failed to activate ${cleanModel}: ${String(error)}`);
    } finally {
      setOllamaBusyAction(null);
    }
  };

  const handleSelectOllamaEmbeddingModel = async (model: string) => {
    const cleanModel = model.trim();
    if (!cleanModel) {
      return;
    }
    setOllamaBusyAction("select_embedding");
    try {
      const result = await selectOllamaEmbeddingModel({
        model: cleanModel,
        baseUrl: ollamaBaseUrlInput.trim() || undefined,
      });
      setOllamaStatus((previous) => ({ ...previous, active_embedding_model: result.model }));
      setOllamaEmbeddingInput(result.model);
      setOllamaMessage(`Embedding model ${cleanModel} is now active for indexing.`);
      await handleRefreshOllamaModels();
    } catch (error) {
      setOllamaMessage(`Failed to activate embedding model ${cleanModel}: ${String(error)}`);
    } finally {
      setOllamaBusyAction(null);
    }
  };

  const handlePullOllamaEmbeddingModel = async (modelOverride?: string) => {
    const model = (modelOverride || ollamaEmbeddingInput).trim();
    const baseUrl = ollamaBaseUrlInput.trim() || undefined;
    if (!model) {
      setOllamaMessage("Enter an embedding model, for example `nomic-embed-text`.");
      return;
    }
    setOllamaBusyAction("pull");
    setOllamaProgress({ status: "starting", percent: 0 });
    setOllamaMessage(`Downloading embedding model ${model}...`);
    try {
      await pullOllamaModel({ model, baseUrl, autoSelect: false });
      await handleSelectOllamaEmbeddingModel(model);
      setOllamaEmbeddingInput(model);
    } catch (error) {
      setOllamaMessage(`Failed to download embedding model ${model}: ${String(error)}`);
      setOllamaBusyAction(null);
    }
  };

  const handleApplyEmbeddingToAllCollections = async () => {
    const model = ollamaEmbeddingInput.trim();
    if (!model) {
      setOllamaMessage("Select an embedding model first.");
      return;
    }
    setOllamaBusyAction("apply_all");
    setOllamaMessage("Applying embedding to all collections and queuing full reindex...");
    try {
      const result = await applyOllamaEmbeddingToAllCollections({
        model,
        baseUrl: ollamaBaseUrlInput.trim() || undefined,
      });
      setOllamaMessage(
        `Applied to ${result.indexes_updated}/${result.indexes_total} collections. Queued ${result.jobs_total} reindex job(s).`,
      );
      await handleRefreshOllamaModels();
    } catch (error) {
      setOllamaMessage(`Failed to apply embedding to collections: ${String(error)}`);
      setOllamaBusyAction(null);
    }
  };

  return {
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
    syncFromStatus,
    handleLiveEvent,
    handleSaveOllamaConfig,
    handleStartOllamaLocally,
    handleRefreshOllamaModels,
    handlePullOllamaModel,
    handleSelectOllamaModel,
    handlePullOllamaEmbeddingModel,
    handleSelectOllamaEmbeddingModel,
    handleApplyEmbeddingToAllCollections,
  };
}
