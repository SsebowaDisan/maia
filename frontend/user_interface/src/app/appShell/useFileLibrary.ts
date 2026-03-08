import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelIngestionJob,
  createFileGroup,
  deleteFileGroup,
  deleteFiles,
  listFileGroups,
  listFiles,
  listIngestionJobs,
  moveFilesToGroup,
  renameFileGroup,
  uploadFiles,
  uploadUrls,
  type BulkDeleteFilesResponse,
  type DeleteFileGroupResponse,
  type FileGroupRecord,
  type FileGroupResponse,
  type FileRecord,
  type IngestionJob,
  type MoveFilesToGroupResponse,
  type UploadResponse,
} from "../../api/client";
import { createFileJobWithFallback, createUrlJobWithFallback } from "./fileLibraryJobCreation";

export function useFileLibrary() {
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploadProgressPercent, setUploadProgressPercent] = useState<number | null>(null);
  const [uploadProgressLabel, setUploadProgressLabel] = useState("");
  const [fileCount, setFileCount] = useState(0);
  const [indexedFiles, setIndexedFiles] = useState<FileRecord[]>([]);
  const [fileGroups, setFileGroups] = useState<FileGroupRecord[]>([]);
  const [defaultIndexId, setDefaultIndexId] = useState<number | null>(null);
  const [ingestionJobs, setIngestionJobs] = useState<IngestionJob[]>([]);
  const [isCancelingUpload, setIsCancelingUpload] = useState(false);
  const activeUploadControllerRef = useRef<AbortController | null>(null);
  const activeUploadStartedAtRef = useRef<number>(0);
  const activeUploadBytesRef = useRef<number>(0);
  const activeFileJobIdRef = useRef<string | null>(null);

  const setProgressFromUploadBytes = (loadedBytes: number, totalBytes: number, label: string) => {
    if (!totalBytes || totalBytes <= 0) {
      setUploadProgressPercent(null);
      setUploadProgressLabel(label);
      return;
    }
    const percent = Math.max(0, Math.min(100, Math.round((loadedBytes / totalBytes) * 100)));
    setUploadProgressPercent(percent);
    setUploadProgressLabel(`${label} ${percent}%`);
  };

  const isAbortError = (error: unknown) => {
    const message = String(error || "").toLowerCase();
    return message.includes("aborterror") || message.includes("upload canceled") || message.includes("aborted");
  };

  const findLikelyJobFromAbortedUpload = (jobs: IngestionJob[]) => {
    const expectedBytes = Math.max(0, Number(activeUploadBytesRef.current || 0));
    const startedAt = Number(activeUploadStartedAtRef.current || 0);
    if (!startedAt) return null;
    return (
      jobs.find((job) => {
        if (job.kind !== "files") return false;
        if (job.status !== "queued" && job.status !== "running") return false;
        const createdAt = job.date_created ? new Date(job.date_created).getTime() : 0;
        if (createdAt && createdAt < startedAt - 10_000) {
          return false;
        }
        if (expectedBytes > 0) {
          const bytesTotal = Math.max(0, Number(job.bytes_total || 0));
          if (bytesTotal !== expectedBytes) {
            return false;
          }
        }
        return true;
      }) || null
    );
  };

  const refreshFileCount = useCallback(async () => {
    const filesPayload = await listFiles();
    setFileCount(filesPayload.files.length);
    setIndexedFiles(filesPayload.files);
    setDefaultIndexId(filesPayload.index_id);
    try {
      const groupsPayload = await listFileGroups({ indexId: filesPayload.index_id });
      setFileGroups(groupsPayload.groups);
    } catch {
      setFileGroups([]);
    }
  }, []);

  const refreshIngestionJobs = useCallback(async () => {
    const jobs = await listIngestionJobs(80);
    setIngestionJobs(jobs);
    const activeFileJob = jobs.find(
      (job) =>
        job.kind === "files" && (job.status === "queued" || job.status === "running"),
    );
    if (!activeFileJob) {
      activeFileJobIdRef.current = null;
      setUploadProgressPercent(null);
      setUploadProgressLabel("");
      return jobs;
    }
    activeFileJobIdRef.current = activeFileJob.id;

    const totalBytes = Math.max(0, Number(activeFileJob.bytes_total || 0));
    const indexedBytes = Math.max(0, Number(activeFileJob.bytes_indexed || 0));
    const percent =
      totalBytes > 0
        ? Math.max(0, Math.min(100, Math.round((indexedBytes / totalBytes) * 100)))
        : Math.max(
            0,
            Math.min(
              100,
              Math.round(
                ((Number(activeFileJob.processed_items || 0) /
                  Math.max(1, Number(activeFileJob.total_items || 0))) *
                  100),
              ),
            ),
          );
    setUploadProgressPercent(percent);
    setUploadProgressLabel(
      `Indexing ${activeFileJob.processed_items}/${activeFileJob.total_items} (${activeFileJob.status})`,
    );
    return jobs;
  }, []);

  useEffect(() => {
    const hasActiveJobs = ingestionJobs.some(
      (job) => job.status === "queued" || job.status === "running",
    );
    if (!hasActiveJobs) {
      return;
    }
    const timer = window.setInterval(() => {
      void Promise.all([refreshIngestionJobs(), refreshFileCount()]);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [ingestionJobs, refreshIngestionJobs, refreshFileCount]);

  const handleUploadFiles = async (
    files: FileList,
    options?: {
      scope?: "persistent" | "chat_temp";
      showStatus?: boolean;
      reindex?: boolean;
      onUploadProgress?: (loadedBytes: number, totalBytes: number) => void;
    },
  ): Promise<UploadResponse> => {
    if (!files.length) {
      throw new Error("No files selected.");
    }

    const scope = options?.scope ?? "persistent";
    const showStatus = options?.showStatus ?? scope !== "chat_temp";
    if (showStatus) {
      setUploadStatus("Uploading files...");
      setUploadProgressPercent(0);
      setUploadProgressLabel("Uploading");
    }
    try {
      const response = await uploadFiles(files, {
        scope,
        reindex: options?.reindex ?? true,
        onUploadProgress: (loadedBytes, totalBytes) => {
          options?.onUploadProgress?.(loadedBytes, totalBytes);
          if (!showStatus) return;
          setProgressFromUploadBytes(loadedBytes, totalBytes, "Uploading");
        },
      });
      const successCount = response.items.filter((item) => item.status === "success").length;
      if (showStatus) {
        setUploadProgressPercent(100);
        setUploadProgressLabel("Processing complete");
        if (response.errors.length > 0) {
          setUploadStatus(`Upload issue: ${response.errors[0]}`);
        } else {
          setUploadStatus(`Indexed ${successCount} file(s).`);
        }
      }
      if (scope !== "chat_temp") {
        await refreshFileCount();
      }
      return response;
    } catch (error) {
      if (showStatus) {
        setUploadProgressPercent(null);
        setUploadProgressLabel("");
        setUploadStatus(`Upload failed: ${String(error)}`);
      }
      throw error;
    } finally {
      if (showStatus) {
        window.setTimeout(() => {
          setUploadProgressPercent(null);
          setUploadProgressLabel("");
        }, 1500);
      }
    }
  };

  const handleUploadFilesForChat = async (
    files: FileList,
    options?: { onUploadProgress?: (loadedBytes: number, totalBytes: number) => void },
  ): Promise<UploadResponse> => {
    return handleUploadFiles(files, {
      scope: "chat_temp",
      showStatus: false,
      onUploadProgress: options?.onUploadProgress,
    });
  };

  const handleUploadUrlsToLibrary = async (
    urlText: string,
    options?: {
      reindex?: boolean;
      web_crawl_depth?: number;
      web_crawl_max_pages?: number;
      web_crawl_same_domain_only?: boolean;
      include_pdfs?: boolean;
      include_images?: boolean;
    },
  ): Promise<UploadResponse> => {
    if (!urlText.trim()) {
      throw new Error("No URLs were provided.");
    }

    setUploadStatus("Indexing URLs...");
    try {
      const response = await uploadUrls(urlText, {
        reindex: options?.reindex ?? false,
        web_crawl_depth: options?.web_crawl_depth ?? 0,
        web_crawl_max_pages: options?.web_crawl_max_pages ?? 0,
        web_crawl_same_domain_only: options?.web_crawl_same_domain_only ?? true,
        include_pdfs: options?.include_pdfs ?? true,
        include_images: options?.include_images ?? true,
      });
      const successCount = response.items.filter((item) => item.status === "success").length;
      if (response.errors.length > 0) {
        setUploadStatus(`URL indexing issue: ${response.errors[0]}`);
      } else {
        setUploadStatus(`Indexed ${successCount} URL source(s).`);
      }
      await refreshFileCount();
      return response;
    } catch (error) {
      setUploadStatus(`URL indexing failed: ${String(error)}`);
      throw error;
    }
  };

  const handleCreateFileIngestionJob = async (
    files: FileList,
    options?: {
      reindex?: boolean;
      groupId?: string;
      scope?: "persistent" | "chat_temp";
      onUploadProgress?: (loadedBytes: number, totalBytes: number) => void;
    },
  ) => {
    return createFileJobWithFallback(files, options, {
      defaultIndexId,
      setUploadStatus,
      setUploadProgressPercent,
      setUploadProgressLabel,
      setProgressFromUploadBytes,
      refreshIngestionJobs,
      refreshFileCount,
      handleUploadFiles,
      isAbortError,
      findLikelyJobFromAbortedUpload,
      activeUploadControllerRef,
      activeUploadStartedAtRef,
      activeUploadBytesRef,
      activeFileJobIdRef,
    });
  };

  const handleCreateUrlIngestionJob = async (
    urlText: string,
    options?: { reindex?: boolean },
  ) => {
    return createUrlJobWithFallback(urlText, options, {
      defaultIndexId,
      setUploadStatus,
      refreshIngestionJobs,
      refreshFileCount,
    });
  };

  const handleCancelFileUpload = async () => {
    if (isCancelingUpload) {
      return;
    }
    setIsCancelingUpload(true);
    try {
      const activeController = activeUploadControllerRef.current;
      if (activeController && !activeController.signal.aborted) {
        setUploadStatus("Canceling upload...");
        activeController.abort();
        activeUploadControllerRef.current = null;
        return;
      }

      const activeJob =
        ingestionJobs.find(
          (job) =>
            job.kind === "files" &&
            (job.status === "queued" || job.status === "running") &&
            (!activeFileJobIdRef.current || job.id === activeFileJobIdRef.current),
        ) ||
        ingestionJobs.find(
          (job) => job.kind === "files" && (job.status === "queued" || job.status === "running"),
        );

      if (!activeJob) {
        setUploadStatus("No active upload job to cancel.");
        return;
      }

      await cancelIngestionJob(activeJob.id);
      activeFileJobIdRef.current = null;
      setUploadStatus("Upload canceled and partial data removed.");
      setUploadProgressPercent(null);
      setUploadProgressLabel("");
      await Promise.all([refreshIngestionJobs(), refreshFileCount()]);
    } catch (error) {
      setUploadStatus(`Cancel failed: ${String(error)}`);
    } finally {
      setIsCancelingUpload(false);
    }
  };

  const handleDeleteFiles = async (fileIds: string[]): Promise<BulkDeleteFilesResponse> => {
    if (!fileIds.length) {
      throw new Error("No files selected.");
    }

    const uniqueIds = Array.from(new Set(fileIds.filter(Boolean)));
    const chunkSize = 100;
    const deletedIds: string[] = [];
    const failed: BulkDeleteFilesResponse["failed"] = [];
    let resolvedIndexId = defaultIndexId ?? 0;

    for (let offset = 0; offset < uniqueIds.length; offset += chunkSize) {
      const chunk = uniqueIds.slice(offset, offset + chunkSize);
      try {
        const response = await deleteFiles(chunk, {
          indexId: defaultIndexId ?? undefined,
        });
        resolvedIndexId = response.index_id;
        deletedIds.push(...response.deleted_ids);
        failed.push(...response.failed);
      } catch (error) {
        const message = String(error);
        failed.push(
          ...chunk.map((fileId) => ({
            file_id: fileId,
            status: "failed",
            message,
          })),
        );
      }
    }

    await refreshFileCount();
    return {
      index_id: resolvedIndexId,
      deleted_ids: deletedIds,
      failed,
    };
  };

  const handleMoveFilesToGroup = async (
    fileIds: string[],
    options?: {
      groupId?: string;
      groupName?: string;
      mode?: "append" | "replace";
    },
  ): Promise<MoveFilesToGroupResponse> => {
    if (!fileIds.length) {
      throw new Error("No files selected.");
    }
    const response = await moveFilesToGroup(fileIds, {
      groupId: options?.groupId,
      groupName: options?.groupName,
      mode: options?.mode ?? "append",
      indexId: defaultIndexId ?? undefined,
    });
    await refreshFileCount();
    return response;
  };

  const handleCreateFileGroup = async (
    name: string,
    fileIds?: string[],
  ): Promise<MoveFilesToGroupResponse> => {
    const response = await createFileGroup(name, fileIds || [], {
      indexId: defaultIndexId ?? undefined,
    });
    await refreshFileCount();
    return response;
  };

  const handleRenameFileGroup = async (
    groupId: string,
    name: string,
  ): Promise<FileGroupResponse> => {
    const response = await renameFileGroup(groupId, name, {
      indexId: defaultIndexId ?? undefined,
    });
    await refreshFileCount();
    return response;
  };

  const handleDeleteFileGroup = async (
    groupId: string,
  ): Promise<DeleteFileGroupResponse> => {
    const response = await deleteFileGroup(groupId, {
      indexId: defaultIndexId ?? undefined,
    });
    await refreshFileCount();
    return response;
  };

  return {
    defaultIndexId,
    fileCount,
    fileGroups,
    isCancelingUpload,
    handleCreateFileGroup,
    handleCreateFileIngestionJob,
    handleCreateUrlIngestionJob,
    handleCancelFileUpload,
    handleDeleteFileGroup,
    handleDeleteFiles,
    handleMoveFilesToGroup,
    handleRenameFileGroup,
    handleUploadFiles,
    handleUploadFilesForChat,
    handleUploadUrlsToLibrary,
    indexedFiles,
    ingestionJobs,
    uploadProgressPercent,
    uploadProgressLabel,
    refreshFileCount,
    refreshIngestionJobs,
    uploadStatus,
  };
}
