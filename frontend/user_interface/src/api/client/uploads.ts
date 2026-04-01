import {
  API_BASE,
  buildApiBaseCandidates,
  fetchApi,
  getActiveUserId,
  buildNetworkError,
  buildRequestUrl,
  isNetworkError,
  request,
  withUserIdHeaders,
} from "./core";
import type {
  BulkDeleteFilesResponse,
  BulkDeleteUrlsResponse,
  DeleteFileGroupResponse,
  FileGroupListResponse,
  FileGroupResponse,
  FileRecord,
  HighlightTargetResponse,
  IngestionJob,
  MoveFilesToGroupResponse,
  UploadResponse,
} from "./types";

function getRawFileUrl(fileId: string): string {
  const base = `${API_BASE}/api/uploads/files/${encodeURIComponent(fileId)}/raw`;
  const activeUserId = getActiveUserId();
  return activeUserId ? `${base}?user_id=${encodeURIComponent(activeUserId)}` : base;
}

function getPdfHighlightTarget(
  fileId: string,
  payload: {
    page?: string;
    text?: string;
    claim_text?: string;
    chunk_id?: string;
    index_id?: number;
  },
) {
  return fetchApi(`/api/uploads/files/${encodeURIComponent(fileId)}/highlight-target`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(async (response) => {
    if (!response.ok) {
      throw new Error((await response.text()) || `Request failed: ${response.status}`);
    }
    const body = (await response.json()) as HighlightTargetResponse;
    const traceId = String(response.headers.get("X-Maia-Trace-Id") || "").trim();
    if (traceId) {
      body.trace_id = traceId;
    }
    return body;
  });
}

const highlightTargetRequestCache = new Map<string, Promise<HighlightTargetResponse>>();
const highlightTargetErrorCooldown = new Map<string, { untilMs: number; message: string }>();
const HIGHLIGHT_TARGET_ERROR_COOLDOWN_MS = 30_000;
const HIGHLIGHT_TARGET_MISSING_FILE_COOLDOWN_MS = 5 * 60_000;
const missingHighlightSourceCooldownByFile = new Map<string, { untilMs: number; message: string }>();

function getPdfHighlightTargetCached(
  fileId: string,
  payload: {
    page?: string;
    text?: string;
    claim_text?: string;
    chunk_id?: string;
    index_id?: number;
  },
) {
  const missingFileCooldown = missingHighlightSourceCooldownByFile.get(fileId);
  if (missingFileCooldown && missingFileCooldown.untilMs > Date.now()) {
    return Promise.reject(
      new Error(missingFileCooldown.message || "Source file is no longer available for this citation."),
    );
  }
  if (missingFileCooldown) {
    missingHighlightSourceCooldownByFile.delete(fileId);
  }
  const cacheKey = `${fileId}::${payload.page || ""}::${payload.text || ""}::${payload.claim_text || ""}::${payload.chunk_id || ""}::${payload.index_id ?? ""}`;
  const cooldown = highlightTargetErrorCooldown.get(cacheKey);
  if (cooldown && cooldown.untilMs > Date.now()) {
    return Promise.reject(new Error(cooldown.message || "Highlight target is temporarily unavailable."));
  }
  if (cooldown) {
    highlightTargetErrorCooldown.delete(cacheKey);
  }
  const existing = highlightTargetRequestCache.get(cacheKey);
  if (existing) {
    return existing;
  }
  const requestPromise = getPdfHighlightTarget(fileId, payload)
    .then((result) => {
      highlightTargetErrorCooldown.delete(cacheKey);
      return result;
    })
    .catch((error) => {
      highlightTargetRequestCache.delete(cacheKey);
      const message =
        error instanceof Error
          ? error.message
          : String(error || "Highlight target request failed.");
      const normalized = String(message || "").toLowerCase();
      if (normalized.includes("404") || normalized.includes("not found")) {
        missingHighlightSourceCooldownByFile.set(fileId, {
          untilMs: Date.now() + HIGHLIGHT_TARGET_MISSING_FILE_COOLDOWN_MS,
          message: "Source file is no longer available for this citation.",
        });
      }
      highlightTargetErrorCooldown.set(cacheKey, {
        untilMs: Date.now() + HIGHLIGHT_TARGET_ERROR_COOLDOWN_MS,
        message,
      });
      throw error instanceof Error ? error : new Error(message);
    });
  highlightTargetRequestCache.set(cacheKey, requestPromise);
  return requestPromise;
}

type UploadProgressCallback = (loadedBytes: number, totalBytes: number) => void;
type UploadRequestOptions = {
  onUploadProgress?: UploadProgressCallback;
  signal?: AbortSignal;
};

function createAbortError() {
  try {
    return new DOMException("Upload canceled.", "AbortError");
  } catch {
    const error = new Error("Upload canceled.");
    error.name = "AbortError";
    return error;
  }
}

async function waitForIngestionJobCompletion(
  jobId: string,
  signal?: AbortSignal,
): Promise<IngestionJob> {
  const startedAt = Date.now();
  const timeoutMs = 20 * 60 * 1000;
  while (true) {
    if (signal?.aborted) {
      throw createAbortError();
    }
    const job = await getIngestionJob(jobId);
    const status = String(job.status || "").trim().toLowerCase();
    if (status === "completed" || status === "completed_with_errors") {
      return job;
    }
    if (status === "failed" || status === "canceled") {
      throw new Error(job.errors?.[0] || job.message || `Ingestion job ${job.status}`);
    }
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error("Ingestion timed out while indexing files.");
    }
    await new Promise<void>((resolve) => window.setTimeout(resolve, 800));
  }
}

function toLegacyUploadResponse(
  files: FileList,
  job: IngestionJob,
): UploadResponse {
  const mappedItems = (job.items || []).map((item, index) => {
    const row = item as Record<string, unknown>;
    const fileName =
      String(row.file_name || row.name || files[index]?.name || "").trim();
    const fileId =
      String(row.file_id || row.source_id || job.file_ids?.[index] || "").trim();
    const status = String(row.status || "").trim() || "failed";
    const message = String(row.message || "").trim();
    return {
      file_name: fileName,
      status,
      message: message || undefined,
      file_id: fileId || undefined,
    };
  });
  return {
    index_id: typeof job.index_id === "number" ? job.index_id : 0,
    file_ids: Array.isArray(job.file_ids) ? job.file_ids : [],
    errors: Array.isArray(job.errors) ? job.errors : [],
    items: mappedItems,
    debug: Array.isArray(job.debug) ? job.debug : [],
  };
}

function requestMultipartWithProgress<T>(
  path: string,
  formData: FormData,
  options?: UploadRequestOptions,
) {
  const onUploadProgress = options?.onUploadProgress;
  const signal = options?.signal;
  if (!onUploadProgress) {
    return request<T>(path, {
      method: "POST",
      body: formData,
      signal,
    });
  }

  const candidates = buildApiBaseCandidates();

  const buildAbortError = () => {
    try {
      return new DOMException("Upload canceled.", "AbortError");
    } catch {
      const error = new Error("Upload canceled.");
      error.name = "AbortError";
      return error;
    }
  };

  const attemptUpload = (candidateIndex: number): Promise<T> =>
    new Promise<T>((resolve, reject) => {
      const candidateBase = candidates[candidateIndex] || API_BASE;
      const url = buildRequestUrl(path, candidateBase);
      const xhr = new XMLHttpRequest();
      let settled = false;
      const retryNextCandidate = (cause: unknown) => {
        if (candidateIndex < candidates.length - 1) {
          resolve(attemptUpload(candidateIndex + 1));
          return;
        }
        reject(buildNetworkError(path, candidates, cause));
      };
      const finish = (callback: () => void) => {
        if (settled) return;
        settled = true;
        if (signal && abortListener) {
          signal.removeEventListener("abort", abortListener);
        }
        callback();
      };
      const abortListener = () => {
        xhr.abort();
      };

      xhr.open("POST", url, true);
      xhr.timeout = 10 * 60 * 1000;

      const headers = withUserIdHeaders();
      headers.forEach((value, key) => {
        xhr.setRequestHeader(key, value);
      });

      if (signal?.aborted) {
        reject(buildAbortError());
        return;
      }
      if (signal) {
        signal.addEventListener("abort", abortListener, { once: true });
      }
      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) {
          return;
        }
        onUploadProgress?.(event.loaded, event.total);
      };
      xhr.onabort = () => {
        finish(() => reject(buildAbortError()));
      };
      xhr.onerror = () => {
        finish(() => retryNextCandidate(new Error("Network error while uploading files.")));
      };
      xhr.ontimeout = () => {
        finish(() => retryNextCandidate(new Error("Upload timed out while sending files.")));
      };
      xhr.onload = () => {
        if (xhr.status < 200 || xhr.status >= 300) {
          const responseError = new Error(xhr.responseText || `Request failed: ${xhr.status}`);
          if ([502, 503, 504].includes(xhr.status)) {
            finish(() => retryNextCandidate(responseError));
            return;
          }
          finish(() => reject(responseError));
          return;
        }
        try {
          finish(() => resolve(JSON.parse(xhr.responseText || "{}") as T));
        } catch (error) {
          finish(() => reject(new Error(`Invalid JSON response: ${String(error)}`)));
        }
      };
      xhr.send(formData);
    });

  return attemptUpload(0).catch((error) => {
    if (isNetworkError(error)) {
      throw buildNetworkError(path, candidates, error);
    }
    throw error;
  });
}

async function uploadFiles(
  files: FileList,
  options?: {
    reindex?: boolean;
    scope?: "persistent" | "chat_temp";
    onUploadProgress?: UploadProgressCallback;
    signal?: AbortSignal;
  },
) {
  const formData = new FormData();
  for (const file of Array.from(files)) {
    formData.append("files", file);
  }
  formData.append("reindex", String(options?.reindex ?? true));
  formData.append("scope", options?.scope ?? "persistent");
  const job = await requestMultipartWithProgress<IngestionJob>(
    "/api/uploads/files/jobs",
    formData,
    {
      onUploadProgress: options?.onUploadProgress,
      signal: options?.signal,
    },
  );
  const completed = await waitForIngestionJobCompletion(job.id, options?.signal);
  return toLegacyUploadResponse(files, completed);
}

function uploadUrls(
  urlText: string,
  options?: {
    reindex?: boolean;
    web_crawl_depth?: number;
    web_crawl_max_pages?: number;
    web_crawl_same_domain_only?: boolean;
    include_pdfs?: boolean;
    include_images?: boolean;
  },
) {
  const urls = urlText
    .split("\n")
    .map((url) => url.trim())
    .filter(Boolean);

  return request<UploadResponse>("/api/uploads/urls", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      urls,
      reindex: options?.reindex ?? true,
      web_crawl_depth: options?.web_crawl_depth ?? 0,
      web_crawl_max_pages: options?.web_crawl_max_pages ?? 0,
      web_crawl_same_domain_only: options?.web_crawl_same_domain_only ?? true,
      include_pdfs: options?.include_pdfs ?? true,
      include_images: options?.include_images ?? true,
    }),
  });
}

function listFiles(options?: { includeChatTemp?: boolean }) {
  const query = new URLSearchParams();
  if (options?.includeChatTemp) {
    query.set("include_chat_temp", "true");
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<{ index_id: number; files: FileRecord[] }>(`/api/uploads/files${suffix}`);
}

function deleteFiles(
  fileIds: string[],
  options?: {
    indexId?: number;
  },
) {
  return request<BulkDeleteFilesResponse>("/api/uploads/files/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_ids: fileIds,
      index_id: options?.indexId,
    }),
  });
}

function deleteUrls(
  urls: string[],
  options?: {
    indexId?: number;
  },
) {
  return request<BulkDeleteUrlsResponse>("/api/uploads/urls/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      urls,
      index_id: options?.indexId,
    }),
  });
}

function listFileGroups(options?: { indexId?: number }) {
  const query = new URLSearchParams();
  if (typeof options?.indexId === "number") {
    query.set("index_id", String(options.indexId));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<FileGroupListResponse>(`/api/uploads/groups${suffix}`);
}

function createFileGroup(
  name: string,
  fileIds: string[],
  options?: {
    indexId?: number;
  },
) {
  const payload = {
    name,
    file_ids: fileIds,
    index_id: options?.indexId,
  };
  const movePayload = {
    file_ids: fileIds,
    group_name: name,
    mode: "append",
    index_id: options?.indexId,
  };

  const isLegacyMethodIssue = (error: unknown) => {
    const text = String(error || "");
    return (
      text.includes("Method Not Allowed") ||
      text.includes("Not Found") ||
      text.includes("404") ||
      text.includes("405")
    );
  };

  const createQuery = new URLSearchParams();
  createQuery.set("name", name);
  if (typeof options?.indexId === "number") {
    createQuery.set("index_id", String(options.indexId));
  }
  if (fileIds.length) {
    createQuery.set("file_ids", fileIds.join(","));
  }

  const attempts: Array<() => Promise<MoveFilesToGroupResponse>> = [
    () =>
      request<MoveFilesToGroupResponse>("/api/uploads/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    () =>
      request<MoveFilesToGroupResponse>("/api/uploads/groups/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(movePayload),
      }),
    () =>
      request<MoveFilesToGroupResponse>("/api/uploads/groups", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    () =>
      request<MoveFilesToGroupResponse>("/api/uploads/groups/move", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(movePayload),
      }),
    () => request<MoveFilesToGroupResponse>(`/api/uploads/groups/create?${createQuery.toString()}`),
  ];

  return (async () => {
    let lastError: unknown = null;
    for (const attempt of attempts) {
      try {
        return await attempt();
      } catch (error) {
        lastError = error;
        if (!isLegacyMethodIssue(error)) {
          throw error;
        }
      }
    }
    if (isLegacyMethodIssue(lastError)) {
      throw new Error(
        "Group API is not available on the running backend process. Restart the Maia API server and refresh the page.",
      );
    }
    throw lastError || new Error("Unable to create group.");
  })();
}

function renameFileGroup(
  groupId: string,
  name: string,
  options?: {
    indexId?: number;
  },
) {
  return request<FileGroupResponse>(`/api/uploads/groups/${encodeURIComponent(groupId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      index_id: options?.indexId,
    }),
  });
}

function deleteFileGroup(
  groupId: string,
  options?: {
    indexId?: number;
  },
) {
  const query = new URLSearchParams();
  if (typeof options?.indexId === "number") {
    query.set("index_id", String(options.indexId));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<DeleteFileGroupResponse>(
    `/api/uploads/groups/${encodeURIComponent(groupId)}${suffix}`,
    {
      method: "DELETE",
    },
  );
}

function moveFilesToGroup(
  fileIds: string[],
  options?: {
    groupId?: string;
    groupName?: string;
    mode?: "append" | "replace";
    indexId?: number;
  },
) {
  return request<MoveFilesToGroupResponse>("/api/uploads/groups/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_ids: fileIds,
      group_id: options?.groupId,
      group_name: options?.groupName,
      mode: options?.mode ?? "append",
      index_id: options?.indexId,
    }),
  });
}

async function createFileIngestionJob(
  files: FileList,
  options?: {
    reindex?: boolean;
    indexId?: number;
    groupId?: string;
    scope?: "persistent" | "chat_temp";
    onUploadProgress?: UploadProgressCallback;
    signal?: AbortSignal;
  },
) {
  const formData = new FormData();
  for (const file of Array.from(files)) {
    formData.append("files", file);
  }
  formData.append("reindex", String(options?.reindex ?? true));
  if (typeof options?.indexId === "number") {
    formData.append("index_id", String(options.indexId));
  }
  if (options?.groupId) {
    formData.append("group_id", options.groupId);
  }
  if (options?.scope) {
    formData.append("scope", options.scope);
  }

  return requestMultipartWithProgress<IngestionJob>(
    "/api/uploads/files/jobs",
    formData,
    {
      onUploadProgress: options?.onUploadProgress,
      signal: options?.signal,
    },
  );
}

function createUrlIngestionJob(
  urlText: string,
  options?: {
    reindex?: boolean;
    indexId?: number;
    web_crawl_depth?: number;
    web_crawl_max_pages?: number;
    web_crawl_same_domain_only?: boolean;
    include_pdfs?: boolean;
    include_images?: boolean;
  },
) {
  const urls = urlText
    .split("\n")
    .map((url) => url.trim())
    .filter(Boolean);

  return request<IngestionJob>("/api/uploads/urls/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      urls,
      index_id: options?.indexId,
      reindex: options?.reindex ?? true,
      web_crawl_depth: options?.web_crawl_depth ?? 0,
      web_crawl_max_pages: options?.web_crawl_max_pages ?? 0,
      web_crawl_same_domain_only: options?.web_crawl_same_domain_only ?? true,
      include_pdfs: options?.include_pdfs ?? true,
      include_images: options?.include_images ?? true,
    }),
  });
}

function listIngestionJobs(limit = 50) {
  return request<IngestionJob[]>(`/api/uploads/jobs?limit=${encodeURIComponent(String(limit))}`);
}

function getIngestionJob(jobId: string) {
  return request<IngestionJob>(`/api/uploads/jobs/${encodeURIComponent(jobId)}`);
}

function cancelIngestionJob(jobId: string) {
  return request<IngestionJob>(`/api/uploads/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
  });
}

function buildRawFileUrl(fileId: string, options?: { indexId?: number; download?: boolean }) {
  const query = new URLSearchParams();
  const activeUserId = getActiveUserId();
  if (activeUserId) {
    query.set("user_id", activeUserId);
  }
  if (typeof options?.indexId === "number") {
    query.set("index_id", String(options.indexId));
  }
  if (options?.download) {
    query.set("download", "true");
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return `${API_BASE}/api/uploads/files/${encodeURIComponent(fileId)}/raw${suffix}`;
}

export {
  buildRawFileUrl,
  createFileGroup,
  createFileIngestionJob,
  createUrlIngestionJob,
  cancelIngestionJob,
  deleteFileGroup,
  deleteFiles,
  deleteUrls,
  getIngestionJob,
  getPdfHighlightTargetCached,
  getPdfHighlightTarget,
  getRawFileUrl,
  listFileGroups,
  listFiles,
  listIngestionJobs,
  moveFilesToGroup,
  renameFileGroup,
  uploadFiles,
  uploadUrls,
};
