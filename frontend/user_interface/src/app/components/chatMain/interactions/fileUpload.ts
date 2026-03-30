import { type ChangeEvent, type Dispatch, type SetStateAction } from "react";
import { getIngestionJob } from "../../../../api/client";
import { formatIngestionJobProgress, formatUploadProgress } from "../ingestionProgress";
import type { ChatMainProps, ComposerAttachment } from "../types";
import { CHAT_MAX_FILE_SIZE_BYTES, CHAT_MAX_TOTAL_BYTES } from "./constants";

type UploadResponseShape = {
  items: { status: string; file_id?: string; message?: string }[];
  errors: string[];
  file_ids: string[];
};

async function waitForIngestionJob(
  jobId: string,
  updatePendingMessage: (text: string) => void,
): Promise<{
  status: string;
  id: string;
  items: { status: string; file_id?: string; message?: string }[];
  errors: string[];
  file_ids: string[];
  message: string;
}> {
  const startedAt = Date.now();
  const timeoutMs = 20 * 60 * 1000;
  while (true) {
    const job = await getIngestionJob(jobId);
    const status = String(job.status || "").toLowerCase();
    if (status === "completed") {
      return job;
    }
    if (status === "failed" || status === "canceled") {
      const reason = job.errors[0] || job.message || `Ingestion job ${job.status}`;
      throw new Error(reason);
    }
    updatePendingMessage(formatIngestionJobProgress(job));

    if (Date.now() - startedAt > timeoutMs) {
      throw new Error("Ingestion timed out while indexing attachments.");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 800));
  }
}

async function trackQueuedIngestionJob({
  jobId,
  pending,
  setAttachments,
  showActionStatus,
}: {
  jobId: string;
  pending: ComposerAttachment[];
  setAttachments: Dispatch<SetStateAction<ComposerAttachment[]>>;
  showActionStatus: (text: string) => void;
}) {
  const pendingIds = new Set(pending.map((attachment) => attachment.id));
  const updatePendingMessage = (text: string) => {
    setAttachments((previous) =>
      previous.map((attachment) =>
        pendingIds.has(attachment.id)
          ? {
              ...attachment,
              status: "indexing",
              message: text,
            }
          : attachment,
      ),
    );
  };

  try {
    const finalJob = await waitForIngestionJob(jobId, updatePendingMessage);
    applyUploadResult({
      pending,
      result: {
        items: finalJob.items,
        errors: finalJob.errors,
        file_ids: finalJob.file_ids,
      },
      setAttachments,
      showActionStatus,
    });
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error || "Upload failed.");
    const compact = errorMessage.length > 250 ? `${errorMessage.slice(0, 247)}...` : errorMessage;
    setAttachments((previous) =>
      previous.map((attachment) =>
        pendingIds.has(attachment.id)
          ? {
              ...attachment,
              status: "error",
              message: errorMessage,
            }
          : attachment,
      ),
    );
    showActionStatus(`Upload failed: ${compact}`);
  }
}

function applyUploadResult({
  pending,
  result,
  setAttachments,
  showActionStatus,
}: {
  pending: ComposerAttachment[];
  result: UploadResponseShape;
  setAttachments: Dispatch<SetStateAction<ComposerAttachment[]>>;
  showActionStatus: (text: string) => void;
}) {
  const failedMessages: string[] = [];
  const pendingUploadIndexById = new Map<string, number>(
    pending.map((attachment, index) => [attachment.id, index]),
  );
  let successCursor = 0;
  setAttachments((previous) =>
    previous.map((attachment) => {
      const uploadIndex = pendingUploadIndexById.get(attachment.id);
      if (typeof uploadIndex !== "number") {
        return attachment;
      }
      const item = result.items[uploadIndex];
      if (item?.status === "success") {
        const mappedFileId =
          item.file_id ||
          result.file_ids[uploadIndex] ||
          result.file_ids[successCursor] ||
          undefined;
        successCursor += 1;
        return {
          ...attachment,
          status: "indexed",
          message: undefined,
          fileId: mappedFileId,
          entityId: mappedFileId,
          kind: "file" as const,
        };
      }
      const failureMessage = item?.message || result.errors[0] || "Upload failed.";
      failedMessages.push(failureMessage);
      return {
        ...attachment,
        status: "error" as const,
        message: failureMessage,
      };
    }),
  );

  if (failedMessages.length > 0) {
    const reason = String(failedMessages[0] || "Upload failed.").trim();
    const compact = reason.length > 250 ? `${reason.slice(0, 247)}...` : reason;
    showActionStatus(`Upload failed: ${compact}`);
    return;
  }
  showActionStatus(`Uploaded ${pending.length} file${pending.length === 1 ? "" : "s"} successfully.`);
}

async function handleComposerFileChange({
  event,
  onCreateFileIngestionJob,
  setAttachments,
  setIsUploading,
  showActionStatus,
}: {
  event: ChangeEvent<HTMLInputElement>;
  onCreateFileIngestionJob: ChatMainProps["onCreateFileIngestionJob"];
  setAttachments: Dispatch<SetStateAction<ComposerAttachment[]>>;
  setIsUploading: Dispatch<SetStateAction<boolean>>;
  showActionStatus: (text: string) => void;
}) {
  const selectedFiles = event.target.files;
  if (!selectedFiles || !selectedFiles.length) {
    return;
  }

  const selectedRows = Array.from(selectedFiles);
  const overSizeFile = selectedRows.find((file) => file.size > CHAT_MAX_FILE_SIZE_BYTES);
  if (overSizeFile) {
    showActionStatus(`File "${overSizeFile.name}" is larger than 512 MB and cannot be uploaded.`);
    event.target.value = "";
    return;
  }
  const totalBytes = selectedRows.reduce((total, file) => total + file.size, 0);
  if (totalBytes > CHAT_MAX_TOTAL_BYTES) {
    showActionStatus("Selected files exceed the 1 GB total upload limit.");
    event.target.value = "";
    return;
  }

  const pending: ComposerAttachment[] = selectedRows.map((file, idx) => ({
    id: `${Date.now()}-${idx}-${file.name}`,
    name: file.name,
    status: "uploading",
    message: "Uploading 0%",
    localUrl: URL.createObjectURL(file),
    mimeType: String(file.type || ""),
    kind: "file",
  }));
  setAttachments((previous) => [...previous, ...pending]);

  const updatePendingMessage = (text: string) => {
    setAttachments((previous) =>
      previous.map((attachment) =>
        pending.some((item) => item.id === attachment.id)
          ? {
              ...attachment,
              status: "uploading",
              message: text,
            }
          : attachment,
      ),
    );
  };

  setIsUploading(true);
  try {
    if (!onCreateFileIngestionJob) {
      throw new Error("File ingestion job endpoint is required for chat uploads.");
    }
    updatePendingMessage("Uploading to server 0%");
    const queued = await onCreateFileIngestionJob(selectedFiles, {
      reindex: false,
      scope: "chat_temp",
      onUploadProgress: (loadedBytes, totalBytesBytes) => {
        updatePendingMessage(formatUploadProgress(loadedBytes, totalBytesBytes, "queueing upload job"));
      },
    });
    setAttachments((previous) =>
      previous.map((attachment) =>
        pending.some((item) => item.id === attachment.id)
          ? {
              ...attachment,
              status: "indexing",
              message: formatIngestionJobProgress(queued),
            }
          : attachment,
      ),
    );
    showActionStatus(
      `Attachment job queued: ${queued.id.slice(0, 8)} (${queued.total_items} file${queued.total_items === 1 ? "" : "s"}).`,
    );
    void trackQueuedIngestionJob({
      jobId: queued.id,
      pending,
      setAttachments,
      showActionStatus,
    });
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error || "Upload failed.");
    const compact = errorMessage.length > 250 ? `${errorMessage.slice(0, 247)}...` : errorMessage;
    setAttachments((previous) =>
      previous.map((attachment) =>
        pending.some((item) => item.id === attachment.id)
          ? {
              ...attachment,
              status: "error" as const,
              message: errorMessage,
            }
          : attachment,
      ),
    );
    showActionStatus(`Upload failed: ${compact}`);
  } finally {
    setIsUploading(false);
    event.target.value = "";
  }
}

export { handleComposerFileChange };
