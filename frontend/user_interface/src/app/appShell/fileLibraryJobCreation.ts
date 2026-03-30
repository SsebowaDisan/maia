import { type MutableRefObject } from "react";
import {
  cancelIngestionJob,
  createFileIngestionJob,
  createUrlIngestionJob,
  type IngestionJob,
} from "../../api/client";
import { formatIngestionJobProgress } from "../components/chatMain/ingestionProgress";

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
    handlers.setUploadStatus(`Failed to queue URL ingestion job: ${String(error)}`);
    throw error;
  }
}

export { createFileJobWithFallback, createUrlJobWithFallback };
