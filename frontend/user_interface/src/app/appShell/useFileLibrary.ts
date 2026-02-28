import { useCallback, useEffect, useState } from "react";
import {
  createFileGroup,
  createFileIngestionJob,
  createUrlIngestionJob,
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

export function useFileLibrary() {
  const [uploadStatus, setUploadStatus] = useState("");
  const [fileCount, setFileCount] = useState(0);
  const [indexedFiles, setIndexedFiles] = useState<FileRecord[]>([]);
  const [fileGroups, setFileGroups] = useState<FileGroupRecord[]>([]);
  const [defaultIndexId, setDefaultIndexId] = useState<number | null>(null);
  const [ingestionJobs, setIngestionJobs] = useState<IngestionJob[]>([]);

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
    },
  ): Promise<UploadResponse> => {
    if (!files.length) {
      throw new Error("No files selected.");
    }

    const scope = options?.scope ?? "persistent";
    const showStatus = options?.showStatus ?? scope !== "chat_temp";
    if (showStatus) {
      setUploadStatus("Uploading files...");
    }
    try {
      const response = await uploadFiles(files, { scope });
      const successCount = response.items.filter((item) => item.status === "success").length;
      if (showStatus) {
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
        setUploadStatus(`Upload failed: ${String(error)}`);
      }
      throw error;
    }
  };

  const handleUploadFilesForChat = async (files: FileList): Promise<UploadResponse> => {
    return handleUploadFiles(files, {
      scope: "chat_temp",
      showStatus: false,
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

  const isMissingJobEndpointError = (error: unknown) => {
    const text = String(error || "");
    return (
      text.includes("Method Not Allowed") ||
      text.includes("Not Found") ||
      text.includes("404") ||
      text.includes("405")
    );
  };

  const handleCreateFileIngestionJob = async (
    files: FileList,
    options?: { reindex?: boolean },
  ) => {
    if (!files.length) {
      throw new Error("No files selected.");
    }

    setUploadStatus("Queueing ingestion job...");
    try {
      const job = await createFileIngestionJob(files, {
        reindex: options?.reindex ?? false,
        indexId: defaultIndexId ?? undefined,
      });
      setUploadStatus(
        `Job queued: ${job.id.slice(0, 8)} (${job.total_items} item${job.total_items === 1 ? "" : "s"}).`,
      );
      await refreshIngestionJobs();
      return job;
    } catch (error) {
      if (isMissingJobEndpointError(error)) {
        setUploadStatus(
          "Async ingestion endpoint unavailable on this server. Uploading with sync fallback...",
        );
        const response = await handleUploadFiles(files);
        await refreshIngestionJobs();
        return {
          id: `fallback-sync-${Date.now()}`,
          user_id: "default",
          kind: "files",
          status: "completed",
          index_id: defaultIndexId,
          reindex: options?.reindex ?? false,
          total_items: files.length,
          processed_items: files.length,
          success_count: response.items.filter((item) => item.status === "success").length,
          failure_count: response.items.filter((item) => item.status !== "success").length,
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
      setUploadStatus(`Failed to queue file ingestion job: ${String(error)}`);
      throw error;
    }
  };

  const handleCreateUrlIngestionJob = async (
    urlText: string,
    options?: { reindex?: boolean },
  ) => {
    if (!urlText.trim()) {
      throw new Error("No URLs were provided.");
    }

    setUploadStatus("Queueing URL ingestion job...");
    try {
      const job = await createUrlIngestionJob(urlText, {
        reindex: options?.reindex ?? false,
        indexId: defaultIndexId ?? undefined,
        web_crawl_depth: 0,
        web_crawl_max_pages: 0,
        web_crawl_same_domain_only: true,
        include_pdfs: true,
        include_images: true,
      });
      setUploadStatus(
        `URL job queued: ${job.id.slice(0, 8)} (${job.total_items} item${job.total_items === 1 ? "" : "s"}).`,
      );
      await refreshIngestionJobs();
      return job;
    } catch (error) {
      if (isMissingJobEndpointError(error)) {
        setUploadStatus(
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
        await refreshFileCount();
        await refreshIngestionJobs();
        const total = urlText
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean).length;
        return {
          id: `fallback-sync-${Date.now()}`,
          user_id: "default",
          kind: "urls",
          status: "completed",
          index_id: defaultIndexId,
          reindex: options?.reindex ?? false,
          total_items: total,
          processed_items: total,
          success_count: response.items.filter((item) => item.status === "success").length,
          failure_count: response.items.filter((item) => item.status !== "success").length,
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
      setUploadStatus(`Failed to queue URL ingestion job: ${String(error)}`);
      throw error;
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
    handleCreateFileGroup,
    handleCreateFileIngestionJob,
    handleCreateUrlIngestionJob,
    handleDeleteFileGroup,
    handleDeleteFiles,
    handleMoveFilesToGroup,
    handleRenameFileGroup,
    handleUploadFiles,
    handleUploadFilesForChat,
    handleUploadUrlsToLibrary,
    indexedFiles,
    ingestionJobs,
    refreshFileCount,
    refreshIngestionJobs,
    uploadStatus,
  };
}
