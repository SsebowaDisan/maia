import type { ChangeEvent, Dispatch, SetStateAction } from "react";
import type { FileGroupRecord, IngestionJob } from "../../../api/client";

const CLIENT_MAX_FILE_SIZE_BYTES = 512 * 1024 * 1024;
const CLIENT_MAX_TOTAL_BYTES = 1024 * 1024 * 1024;

type CreateUploadActionsParams = {
  onCreateFileIngestionJob?: (
    files: FileList,
    options?: { reindex?: boolean; groupId?: string },
  ) => Promise<IngestionJob>;
  onUploadUrls?: (
    urlText: string,
    options?: {
      reindex?: boolean;
      web_crawl_depth?: number;
      web_crawl_max_pages?: number;
      web_crawl_same_domain_only?: boolean;
      include_pdfs?: boolean;
      include_images?: boolean;
    },
  ) => Promise<{
    file_ids: string[];
    errors: string[];
    items: { status: string; file_id?: string }[];
  }>;
  onMoveFilesToGroup?: (
    fileIds: string[],
    options?: { groupId?: string; groupName?: string; mode?: "append" | "replace" },
  ) => Promise<{
    group: { id: string; name: string };
    moved_ids: string[];
    skipped_ids: string[];
  }>;
  onRefreshIngestionJobs?: () => Promise<void>;
  onRefreshFiles?: () => Promise<void>;
  fileGroups: FileGroupRecord[];
  uploadGroupId: string;
  urlText: string;
  forceReindex: boolean;
  setIsSubmitting: Dispatch<SetStateAction<boolean>>;
  setActionMessage: Dispatch<SetStateAction<string>>;
  setUrlText: Dispatch<SetStateAction<string>>;
};

function createUploadActions({
  onCreateFileIngestionJob,
  onUploadUrls,
  onMoveFilesToGroup,
  onRefreshIngestionJobs,
  onRefreshFiles,
  fileGroups,
  uploadGroupId,
  urlText,
  forceReindex,
  setIsSubmitting,
  setActionMessage,
  setUrlText,
}: CreateUploadActionsParams) {
  const handleFileInputChange = async (event: ChangeEvent<HTMLInputElement>) => {
    if (!event.target.files || !event.target.files.length) return;
    if (!onCreateFileIngestionJob) {
      setActionMessage("Upload action is not available.");
      window.setTimeout(() => setActionMessage(""), 2400);
      event.target.value = "";
      return;
    }
    if (!fileGroups.length) {
      setActionMessage("Create a group first before uploading files.");
      window.setTimeout(() => setActionMessage(""), 2600);
      event.target.value = "";
      return;
    }
    if (!uploadGroupId) {
      setActionMessage("Choose a destination group before uploading.");
      window.setTimeout(() => setActionMessage(""), 2600);
      event.target.value = "";
      return;
    }

    setIsSubmitting(true);
    try {
      const selectedFiles = Array.from(event.target.files);
      const totalBytes = selectedFiles.reduce((total, file) => total + file.size, 0);
      const overSizeFile = selectedFiles.find((file) => file.size > CLIENT_MAX_FILE_SIZE_BYTES);
      if (overSizeFile) {
        setActionMessage(
          `File "${overSizeFile.name}" is larger than 512 MB and cannot be uploaded in one request.`,
        );
        window.setTimeout(() => setActionMessage(""), 3400);
        return;
      }
      if (totalBytes > CLIENT_MAX_TOTAL_BYTES) {
        setActionMessage("Selected files exceed 1 GB total request limit.");
        window.setTimeout(() => setActionMessage(""), 3200);
        return;
      }
      if (onCreateFileIngestionJob) {
        const queued = await onCreateFileIngestionJob(event.target.files, {
          reindex: forceReindex,
          groupId: uploadGroupId,
        });
        setActionMessage(
          `Queued ingestion job ${queued.id.slice(0, 8)} for ${queued.total_items} file(s). Files will appear in the selected group after indexing.`,
        );
        await onRefreshIngestionJobs?.();
        await onRefreshFiles?.();
        window.setTimeout(() => setActionMessage(""), 3200);
        return;
      }
    } catch (error) {
      setActionMessage(`Upload failed: ${String(error)}`);
      window.setTimeout(() => setActionMessage(""), 2600);
    } finally {
      setIsSubmitting(false);
      event.target.value = "";
    }
  };

  const handleUrlIndex = async () => {
    if (!urlText.trim()) return;
    if (!onUploadUrls || !onMoveFilesToGroup) {
      setActionMessage("URL indexing is not available.");
      window.setTimeout(() => setActionMessage(""), 2400);
      return;
    }
    if (!fileGroups.length) {
      setActionMessage("Create a group first before indexing URLs.");
      window.setTimeout(() => setActionMessage(""), 2600);
      return;
    }
    if (!uploadGroupId) {
      setActionMessage("Choose a destination group before indexing URLs.");
      window.setTimeout(() => setActionMessage(""), 2600);
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await onUploadUrls(urlText, {
        reindex: forceReindex,
        web_crawl_depth: 0,
        web_crawl_max_pages: 0,
        web_crawl_same_domain_only: true,
        include_pdfs: true,
        include_images: true,
      });
      const successFileIds = extractSuccessfulFileIds(response);
      if (!successFileIds.length) {
        setActionMessage(response.errors[0] || "No URL content was indexed.");
        window.setTimeout(() => setActionMessage(""), 2600);
        return;
      }
      const moveResponse = await onMoveFilesToGroup(successFileIds, { groupId: uploadGroupId, mode: "append" });
      const failedCount = response.items.filter((item) => item.status !== "success").length;
      setActionMessage(
        failedCount > 0
          ? `Indexed ${successFileIds.length} source(s) to "${moveResponse.group.name}", ${failedCount} failed.`
          : `Indexed ${successFileIds.length} source(s) to "${moveResponse.group.name}".`,
      );
      await onRefreshIngestionJobs?.();
      await onRefreshFiles?.();
      setUrlText("");
      window.setTimeout(() => setActionMessage(""), 2600);
    } catch (error) {
      setActionMessage(`URL indexing failed: ${String(error)}`);
      window.setTimeout(() => setActionMessage(""), 2600);
    } finally {
      setIsSubmitting(false);
    }
  };

  return {
    handleFileInputChange,
    handleUrlIndex,
  };
}

export { createUploadActions };
