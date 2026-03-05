import { ACTIVE_USER_ID, API_BASE, request, withUserIdQuery } from "./core";
import type {
  BulkDeleteFilesResponse,
  BulkDeleteUrlsResponse,
  DeleteFileGroupResponse,
  FileGroupListResponse,
  FileGroupResponse,
  FileRecord,
  IngestionJob,
  MoveFilesToGroupResponse,
  UploadResponse,
} from "./types";

function getRawFileUrl(fileId: string): string {
  return `${API_BASE}/api/uploads/files/${encodeURIComponent(fileId)}/raw`;
}

type UploadProgressCallback = (loadedBytes: number, totalBytes: number) => void;
type UploadRequestOptions = {
  onUploadProgress?: UploadProgressCallback;
  signal?: AbortSignal;
};

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

  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let settled = false;
    const relativePath = withUserIdQuery(path);
    const url = `${API_BASE}${relativePath}`;
    const buildAbortError = () => {
      try {
        return new DOMException("Upload canceled.", "AbortError");
      } catch {
        const error = new Error("Upload canceled.");
        error.name = "AbortError";
        return error;
      }
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
    if (ACTIVE_USER_ID) {
      xhr.setRequestHeader("X-User-Id", ACTIVE_USER_ID);
    }
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
      onUploadProgress(event.loaded, event.total);
    };
    xhr.onabort = () => {
      finish(() => reject(buildAbortError()));
    };
    xhr.onerror = () => {
      finish(() => reject(new Error("Network error while uploading files.")));
    };
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        finish(() => reject(new Error(xhr.responseText || `Request failed: ${xhr.status}`)));
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

  return requestMultipartWithProgress<UploadResponse>(
    "/api/uploads/files",
    formData,
    {
      onUploadProgress: options?.onUploadProgress,
      signal: options?.signal,
    },
  );
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
  getRawFileUrl,
  listFileGroups,
  listFiles,
  listIngestionJobs,
  moveFilesToGroup,
  renameFileGroup,
  uploadFiles,
  uploadUrls,
};
