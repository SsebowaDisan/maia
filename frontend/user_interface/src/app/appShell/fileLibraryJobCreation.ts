import { type MutableRefObject } from "react";
import {
  cancelIngestionJob,
  createFileIngestionJob,
  createUrlIngestionJob,
  moveFilesToGroup,
  uploadUrls,
  type IngestionJob,
} from "../../api/client";
import type { UploadResponse } from "../../api/client";
import { formatIngestionJobProgress } from "../components/chatMain/ingestionProgress";

function isMissingJobEndpointError(error: unknown) {
  const text = String(error || "");
  return (
    text.includes("Method Not Allowed") ||
    text.includes("Not Found") ||
    text.includes("404") ||
    text.includes("405")
  );
}

type FileJobOptions = {
  reindex?: boolean;
  groupId?: string;
  scope?: "persistent" | "chat_temp";
  onUploadProgress?: (loadedBytes: number, totalBytes: number) => void;
};

type UrlJobOptions = {
  reindex?: boolean;
};

type FileJobHandlers = {
  defaultIndexId: number | null;
  setUploadStatus: (value: string) => void;
  setUploadProgressPercent: (value: number | null) => void;
  setUploadProgressLabel: (value: string) => void;
  setProgressFromUploadBytes: (loadedBytes: number, totalBytes: number, label: string) => void;
  refreshIngestionJobs: () => Promise<IngestionJob[]>;
  refreshFileCount: () => Promise<void>;
  handleUploadFiles: (files: FileList, options?: {
    scope?: "persistent" | "chat_temp";
    showStatus?: boolean;
    reindex?: boolean;
    onUploadProgress?: (loadedBytes: number, totalBytes: number) => void;
  }) => Promise<UploadResponse>;
  isAbortError: (error: unknown) => boolean;
  findLikelyJobFromAbortedUpload: (jobs: IngestionJob[]) => IngestionJob | null;
  activeUploadControllerRef: MutableRefObject<AbortController | null>;
  activeUploadStartedAtRef: MutableRefObject<number>;
  activeUploadBytesRef: MutableRefObject<number>;
  activeFileJobIdRef: MutableRefObject<string | null>;
};

async function createFileJobWithFallback(
  files: FileList,
  options: FileJobOptions | undefined,
  handlers: FileJobHandlers,
) {
  if (!files.length) {
    throw new Error("No files selected.");
  }

  handlers.setUploadStatus("Queueing ingestion job...");
  handlers.setUploadProgressPercent(0);
  handlers.setUploadProgressLabel("Uploading");
  const uploadBytes = Array.from(files).reduce((total, file) => total + file.size, 0);
  const controller = new AbortController();
  handlers.activeUploadControllerRef.current = controller;
  handlers.activeUploadStartedAtRef.current = Date.now();
  handlers.activeUploadBytesRef.current = uploadBytes;
  try {
    const job = await createFileIngestionJob(files, {
      reindex: options?.reindex ?? false,
      indexId: handlers.defaultIndexId ?? undefined,
      groupId: options?.groupId,
      scope: options?.scope ?? "persistent",
      signal: controller.signal,
      onUploadProgress: (loadedBytes, totalBytes) => {
        options?.onUploadProgress?.(loadedBytes, totalBytes);
        handlers.setProgressFromUploadBytes(loadedBytes, totalBytes, "Uploading");
      },
    });
    handlers.activeUploadControllerRef.current = null;
    handlers.activeFileJobIdRef.current = job.id;
    handlers.setUploadProgressPercent(0);
    handlers.setUploadProgressLabel(formatIngestionJobProgress(job));
    handlers.setUploadStatus(
      `Job queued: ${job.id.slice(0, 8)} (${job.total_items} item${job.total_items === 1 ? "" : "s"}).`,
    );
    await handlers.refreshIngestionJobs();
    return job;
  } catch (error) {
    handlers.activeUploadControllerRef.current = null;
    if (handlers.isAbortError(error)) {
      handlers.setUploadStatus("Upload canceled.");
      handlers.setUploadProgressPercent(null);
      handlers.setUploadProgressLabel("");
      const jobsAfterAbort = await handlers.refreshIngestionJobs();
      const likelyJob = handlers.findLikelyJobFromAbortedUpload(jobsAfterAbort || []);
      if (likelyJob) {
        try {
          await cancelIngestionJob(likelyJob.id);
          await Promise.all([handlers.refreshIngestionJobs(), handlers.refreshFileCount()]);
        } catch {
          // Best-effort cleanup for race conditions when backend already queued a job.
        }
      }
      throw new Error("Upload canceled.");
    }
    if (isMissingJobEndpointError(error)) {
      handlers.setUploadStatus(
        "Async ingestion endpoint unavailable on this server. Uploading with sync fallback...",
      );
      const response = await handlers.handleUploadFiles(files, {
        reindex: options?.reindex ?? false,
        scope: options?.scope ?? "persistent",
        onUploadProgress: options?.onUploadProgress,
      });
      const successFileIds = response.items
        .filter((item) => item.status === "success" && item.file_id)
        .map((item) => String(item.file_id));
      if (options?.groupId && successFileIds.length > 0 && (options?.scope ?? "persistent") === "persistent") {
        try {
          await moveFilesToGroup(successFileIds, {
            groupId: options.groupId,
            mode: "append",
            indexId: handlers.defaultIndexId ?? undefined,
          });
        } catch {
          // Preserve sync fallback result even if post-move fails.
        }
      }
      await handlers.refreshIngestionJobs();
      return {
        id: `fallback-sync-${Date.now()}`,
        user_id: "default",
        kind: "files",
        status: "completed",
        index_id: handlers.defaultIndexId,
        reindex: options?.reindex ?? false,
        total_items: files.length,
        processed_items: files.length,
        success_count: response.items.filter((item) => item.status === "success").length,
        failure_count: response.items.filter((item) => item.status !== "success").length,
        bytes_total: Array.from(files).reduce((total, file) => total + file.size, 0),
        bytes_persisted: Array.from(files).reduce((total, file) => total + file.size, 0),
        bytes_indexed: Array.from(files).reduce((total, file) => total + file.size, 0),
        items: response.items,
        errors: response.errors,
        file_ids: response.file_ids,
        debug: response.debug,
        message: "Completed via sync upload fallback.",
        date_created: new Date().toISOString(),
        date_updated: new Date().toISOString(),
        date_started: new Date().toISOString(),
        date_finished: new Date().toISOString(),
      } as IngestionJob;
    }
    handlers.setUploadStatus(`Failed to queue file ingestion job: ${String(error)}`);
    handlers.setUploadProgressPercent(null);
    handlers.setUploadProgressLabel("");
    throw error;
  } finally {
    handlers.activeUploadControllerRef.current = null;
    handlers.activeUploadBytesRef.current = 0;
    handlers.activeUploadStartedAtRef.current = 0;
  }
}

async function createUrlJobWithFallback(
  urlText: string,
  options: UrlJobOptions | undefined,
  handlers: {
    defaultIndexId: number | null;
    setUploadStatus: (value: string) => void;
    refreshIngestionJobs: () => Promise<IngestionJob[]>;
    refreshFileCount: () => Promise<void>;
  },
) {
  if (!urlText.trim()) {
    throw new Error("No URLs were provided.");
  }

  handlers.setUploadStatus("Queueing URL ingestion job...");
  try {
    const job = await createUrlIngestionJob(urlText, {
      reindex: options?.reindex ?? false,
      indexId: handlers.defaultIndexId ?? undefined,
      web_crawl_depth: 0,
      web_crawl_max_pages: 0,
      web_crawl_same_domain_only: true,
      include_pdfs: true,
      include_images: true,
    });
    handlers.setUploadStatus(
      `URL job queued: ${job.id.slice(0, 8)} (${job.total_items} item${job.total_items === 1 ? "" : "s"}).`,
    );
    await handlers.refreshIngestionJobs();
    return job;
  } catch (error) {
    if (isMissingJobEndpointError(error)) {
      handlers.setUploadStatus(
        "Async URL endpoint unavailable on this server. Indexing URLs with sync fallback...",
      );
      const response = await uploadUrls(urlText, {
        reindex: options?.reindex ?? false,
        web_crawl_depth: 0,
        web_crawl_max_pages: 0,
        web_crawl_same_domain_only: true,
        include_pdfs: true,
        include_images: true,
      });
      await handlers.refreshFileCount();
      await handlers.refreshIngestionJobs();
      const total = urlText
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean).length;
      return {
        id: `fallback-sync-${Date.now()}`,
        user_id: "default",
        kind: "urls",
        status: "completed",
        index_id: handlers.defaultIndexId,
        reindex: options?.reindex ?? false,
        total_items: total,
        processed_items: total,
        success_count: response.items.filter((item) => item.status === "success").length,
        failure_count: response.items.filter((item) => item.status !== "success").length,
        bytes_total: 0,
        bytes_persisted: 0,
        bytes_indexed: 0,
        items: response.items,
        errors: response.errors,
        file_ids: response.file_ids,
        debug: response.debug,
        message: "Completed via sync URL fallback.",
        date_created: new Date().toISOString(),
        date_updated: new Date().toISOString(),
        date_started: new Date().toISOString(),
        date_finished: new Date().toISOString(),
      } as IngestionJob;
    }
    handlers.setUploadStatus(`Failed to queue URL ingestion job: ${String(error)}`);
    throw error;
  }
}

export { createFileJobWithFallback, createUrlJobWithFallback };
