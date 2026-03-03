import type { ChangeEvent, Dispatch, DragEvent, RefObject, SetStateAction } from "react";
import type { FileGroupRecord, FileRecord, IngestionJob } from "../../../api/client";
import { extractSuccessfulFileIds } from "./helpers";
import type { DeleteConfirmationState, PendingDeleteJob } from "./types";

const CLIENT_MAX_FILE_SIZE_BYTES = 512 * 1024 * 1024;
const CLIENT_MAX_TOTAL_BYTES = 1024 * 1024 * 1024;

interface UseFilesViewActionsParams {
  onDeleteFiles?: (fileIds: string[]) => Promise<{
    deleted_ids: string[];
    failed: { file_id: string; status?: string; message?: string }[];
  }>;
  onMoveFilesToGroup?: (
    fileIds: string[],
    options?: { groupId?: string; groupName?: string; mode?: "append" | "replace" },
  ) => Promise<{
    group: { id: string; name: string };
    moved_ids: string[];
    skipped_ids: string[];
  }>;
  onCreateFileGroup?: (name: string, fileIds?: string[]) => Promise<{
    group: { id: string; name: string };
    moved_ids: string[];
  }>;
  onRenameFileGroup?: (groupId: string, name: string) => Promise<{ group: { name: string } }>;
  onDeleteFileGroup?: (groupId: string) => Promise<unknown>;
  onUploadFiles?: (
    files: FileList,
    options?: { scope?: "persistent" | "chat_temp"; reindex?: boolean },
  ) => Promise<{
    file_ids: string[];
    errors: string[];
    items: { status: string; file_id?: string }[];
  }>;
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
  onRefreshIngestionJobs?: () => Promise<void>;
  onRefreshFiles?: () => Promise<void>;
  fileGroups: FileGroupRecord[];
  selectedFiles: FileRecord[];
  selectedFileIds: string[];
  pendingDelete: PendingDeleteJob | null;
  deleteConfirmation: DeleteConfirmationState | null;
  deleteConfirmText: string;
  targetGroupId: string;
  quickGroupName: string;
  manageGroupId: string;
  manageGroupName: string;
  uploadGroupId: string;
  urlText: string;
  forceReindex: boolean;
  selectedPdfPreviewUrl: string | null;
  isDeletingSelection: boolean;
  pdfPreviewRef: RefObject<HTMLDivElement | null>;
  setActionMessage: Dispatch<SetStateAction<string>>;
  setIsDeletingSelection: Dispatch<SetStateAction<boolean>>;
  setPendingDelete: Dispatch<SetStateAction<PendingDeleteJob | null>>;
  setSelectedFileIds: Dispatch<SetStateAction<string[]>>;
  setDeleteConfirmation: Dispatch<SetStateAction<DeleteConfirmationState | null>>;
  setDeleteConfirmText: Dispatch<SetStateAction<string>>;
  setDraggingFileId: Dispatch<SetStateAction<string | null>>;
  setDragOverGroupId: Dispatch<SetStateAction<string | null>>;
  setIsMovingSelection: Dispatch<SetStateAction<boolean>>;
  setTargetGroupId: Dispatch<SetStateAction<string>>;
  setActiveGroupFilter: Dispatch<SetStateAction<string>>;
  setIsCreatingGroup: Dispatch<SetStateAction<boolean>>;
  setQuickGroupName: Dispatch<SetStateAction<string>>;
  setManageGroupId: Dispatch<SetStateAction<string>>;
  setManageGroupName: Dispatch<SetStateAction<string>>;
  setShowCreateGroupModal: Dispatch<SetStateAction<boolean>>;
  setIsManagingGroup: Dispatch<SetStateAction<boolean>>;
  setIsSubmitting: Dispatch<SetStateAction<boolean>>;
  setUrlText: Dispatch<SetStateAction<string>>;
}

function useFilesViewActions({
  onDeleteFiles,
  onMoveFilesToGroup,
  onCreateFileGroup,
  onRenameFileGroup,
  onDeleteFileGroup,
  onUploadFiles,
  onCreateFileIngestionJob,
  onUploadUrls,
  onRefreshIngestionJobs,
  onRefreshFiles,
  fileGroups,
  selectedFiles,
  selectedFileIds,
  pendingDelete,
  deleteConfirmation,
  deleteConfirmText,
  targetGroupId,
  quickGroupName,
  manageGroupId,
  manageGroupName,
  uploadGroupId,
  urlText,
  forceReindex,
  selectedPdfPreviewUrl,
  isDeletingSelection,
  pdfPreviewRef,
  setActionMessage,
  setIsDeletingSelection,
  setPendingDelete,
  setSelectedFileIds,
  setDeleteConfirmation,
  setDeleteConfirmText,
  setDraggingFileId,
  setDragOverGroupId,
  setIsMovingSelection,
  setTargetGroupId,
  setActiveGroupFilter,
  setIsCreatingGroup,
  setQuickGroupName,
  setManageGroupId,
  setManageGroupName,
  setShowCreateGroupModal,
  setIsManagingGroup,
  setIsSubmitting,
  setUrlText,
}: UseFilesViewActionsParams) {
  const focusPdfPreview = () => {
    if (!selectedPdfPreviewUrl) {
      setActionMessage("Select at least one PDF to preview.");
      window.setTimeout(() => setActionMessage(""), 2200);
      return;
    }
    pdfPreviewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const clearPendingDelete = () => {
    if (!pendingDelete) return;
    window.clearTimeout(pendingDelete.timeoutId);
    setPendingDelete(null);
  };

  const commitPendingDelete = async (fileIds: string[]) => {
    if (!fileIds.length || !onDeleteFiles) return;
    setIsDeletingSelection(true);
    try {
      const response = await onDeleteFiles(fileIds);
      const deletedCount = response.deleted_ids.length;
      const failedCount = response.failed.length;
      const failedSnippet =
        failedCount > 0
          ? ` ${response.failed
              .slice(0, 2)
              .map((item) => item.message || item.status || item.file_id)
              .join(" | ")}`
          : "";
      setActionMessage(
        failedCount > 0
          ? `Deleted ${deletedCount} file(s), ${failedCount} failed.${failedSnippet}`
          : `Deleted ${deletedCount} file(s).`,
      );
      setSelectedFileIds((previous) => previous.filter((fileId) => !response.deleted_ids.includes(fileId)));
    } catch (error) {
      setActionMessage(`Delete failed: ${String(error)}`);
    } finally {
      setIsDeletingSelection(false);
      setPendingDelete(null);
      window.setTimeout(() => setActionMessage(""), 2600);
    }
  };

  const queueDeletion = (fileIds: string[]) => {
    if (!fileIds.length) return;
    if (pendingDelete) {
      window.clearTimeout(pendingDelete.timeoutId);
    }
    const expiresAt = Date.now() + 5000;
    const timeoutId = window.setTimeout(() => {
      void commitPendingDelete(fileIds);
    }, 5000);
    setPendingDelete({ fileIds, count: fileIds.length, expiresAt, timeoutId });
    setActionMessage(`Queued ${fileIds.length} file(s) for deletion. Undo within 5s.`);
  };

  const handleDeleteSelected = () => {
    if (!selectedFiles.length || !onDeleteFiles || isDeletingSelection) return;
    const fileIds = Array.from(new Set(selectedFiles.map((file) => file.id)));
    if (!fileIds.length) return;
    setDeleteConfirmation({
      fileIds,
      count: fileIds.length,
      primaryName: selectedFiles[0]?.name || "selected file",
    });
    setDeleteConfirmText("");
  };

  const handleCancelDeleteConfirmation = () => {
    setDeleteConfirmation(null);
    setDeleteConfirmText("");
  };

  const handleConfirmDeleteAfterTyping = () => {
    if (!deleteConfirmation) return;
    if (deleteConfirmText.trim().toLowerCase() !== "delete") return;
    queueDeletion(deleteConfirmation.fileIds);
    setDeleteConfirmation(null);
    setDeleteConfirmText("");
  };

  const handleUndoDelete = () => {
    clearPendingDelete();
    setActionMessage("Deletion canceled.");
    window.setTimeout(() => setActionMessage(""), 2200);
  };

  const handleDeleteNow = () => {
    if (!pendingDelete) return;
    const fileIds = [...pendingDelete.fileIds];
    window.clearTimeout(pendingDelete.timeoutId);
    setPendingDelete(null);
    void commitPendingDelete(fileIds);
  };

  const startFileDrag = (event: DragEvent<HTMLElement>, fileId: string) => {
    if (!onMoveFilesToGroup) return;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", fileId);
    setDraggingFileId(fileId);
  };

  const endFileDrag = () => {
    setDraggingFileId(null);
    setDragOverGroupId(null);
  };

  const moveIntoGroup = async (fileIds: string[], groupId: string, source: "manual" | "drag") => {
    if (!fileIds.length || !onMoveFilesToGroup || !groupId) return;
    setIsMovingSelection(true);
    try {
      const response = await onMoveFilesToGroup(fileIds, { groupId, mode: "append" });
      setTargetGroupId(response.group.id);
      setActiveGroupFilter(response.group.id);
      const movedCount = response.moved_ids.length;
      const skippedCount = response.skipped_ids.length;
      const prefix = source === "drag" ? "Dropped" : "Moved";
      setActionMessage(
        skippedCount > 0
          ? `${prefix} ${movedCount} file(s) into "${response.group.name}", ${skippedCount} skipped.`
          : `${prefix} ${movedCount} file(s) into "${response.group.name}".`,
      );
    } catch (error) {
      setActionMessage(`Move failed: ${String(error)}`);
    } finally {
      setIsMovingSelection(false);
      window.setTimeout(() => setActionMessage(""), 2600);
    }
  };

  const dropFilesIntoGroup = async (groupId: string, sourceFileId: string | null) => {
    if (!onMoveFilesToGroup) return;
    const fromSelection = sourceFileId && selectedFileIds.includes(sourceFileId) && selectedFileIds.length > 0;
    const fileIds = fromSelection ? [...selectedFileIds] : sourceFileId ? [sourceFileId] : [];
    if (!fileIds.length) {
      setActionMessage("Select or drag a file first.");
      window.setTimeout(() => setActionMessage(""), 2200);
      return;
    }
    await moveIntoGroup(fileIds, groupId, "drag");
  };

  const handleMoveSelected = async () => {
    if (!selectedFiles.length || !onMoveFilesToGroup) return;
    if (!targetGroupId) {
      setActionMessage("Choose a destination group.");
      window.setTimeout(() => setActionMessage(""), 2400);
      return;
    }
    await moveIntoGroup(
      selectedFiles.map((file) => file.id),
      targetGroupId,
      "manual",
    );
  };

  const handleCreateQuickGroup = async () => {
    if (!onCreateFileGroup) return;
    const cleanName = quickGroupName.trim();
    if (!cleanName) {
      setActionMessage("Enter a group name.");
      window.setTimeout(() => setActionMessage(""), 2200);
      return;
    }
    setIsCreatingGroup(true);
    try {
      const selectedIds = selectedFiles.map((file) => file.id);
      const response = await onCreateFileGroup(cleanName, selectedIds);
      setQuickGroupName("");
      setActiveGroupFilter(response.group.id);
      setManageGroupId(response.group.id);
      setManageGroupName(response.group.name);
      setTargetGroupId(response.group.id);
      setShowCreateGroupModal(false);
      if (selectedIds.length > 0) {
        setActionMessage(`Created "${response.group.name}" and added ${response.moved_ids.length} selected file(s).`);
      } else {
        setActionMessage(`Created "${response.group.name}".`);
      }
    } catch (error) {
      setActionMessage(`Create group failed: ${String(error)}`);
    } finally {
      setIsCreatingGroup(false);
      window.setTimeout(() => setActionMessage(""), 2600);
    }
  };

  const handleRenameGroup = async () => {
    if (!manageGroupId || !onRenameFileGroup) return;
    const cleanName = manageGroupName.trim();
    if (!cleanName) {
      setActionMessage("Group name is required.");
      window.setTimeout(() => setActionMessage(""), 2400);
      return;
    }
    setIsManagingGroup(true);
    try {
      const response = await onRenameFileGroup(manageGroupId, cleanName);
      setManageGroupName(response.group.name);
      setActionMessage(`Renamed group to "${response.group.name}".`);
    } catch (error) {
      setActionMessage(`Rename failed: ${String(error)}`);
    } finally {
      setIsManagingGroup(false);
      window.setTimeout(() => setActionMessage(""), 2600);
    }
  };

  const handleDeleteGroup = async () => {
    if (!manageGroupId || !onDeleteFileGroup) return;
    const group = fileGroups.find((item) => item.id === manageGroupId);
    const groupName = group?.name || "this group";
    const shouldDelete = window.confirm(`Delete group "${groupName}"?`);
    if (!shouldDelete) return;

    setIsManagingGroup(true);
    try {
      await onDeleteFileGroup(manageGroupId);
      setManageGroupId("");
      setManageGroupName("");
      setActionMessage(`Deleted group "${groupName}".`);
    } catch (error) {
      setActionMessage(`Delete group failed: ${String(error)}`);
    } finally {
      setIsManagingGroup(false);
      window.setTimeout(() => setActionMessage(""), 2600);
    }
  };

  const handleFileInputChange = async (event: ChangeEvent<HTMLInputElement>) => {
    if (!event.target.files || !event.target.files.length) return;
    if (!onUploadFiles || !onMoveFilesToGroup) {
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

      const response = await onUploadFiles(event.target.files, { reindex: forceReindex, scope: "persistent" });
      const successFileIds = extractSuccessfulFileIds(response);
      if (!successFileIds.length) {
        setActionMessage(response.errors[0] || "No files were indexed.");
        window.setTimeout(() => setActionMessage(""), 2600);
        return;
      }
      const moveResponse = await onMoveFilesToGroup(successFileIds, { groupId: uploadGroupId, mode: "append" });
      const failedCount = response.items.filter((item) => item.status !== "success").length;
      setActionMessage(
        failedCount > 0
          ? `Uploaded ${successFileIds.length} file(s) to "${moveResponse.group.name}", ${failedCount} failed.`
          : `Uploaded ${successFileIds.length} file(s) to "${moveResponse.group.name}".`,
      );
      await onRefreshIngestionJobs?.();
      await onRefreshFiles?.();
      window.setTimeout(() => setActionMessage(""), 2600);
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
    dropFilesIntoGroup,
    endFileDrag,
    focusPdfPreview,
    handleCancelDeleteConfirmation,
    handleConfirmDeleteAfterTyping,
    handleCreateQuickGroup,
    handleDeleteGroup,
    handleDeleteNow,
    handleDeleteSelected,
    handleFileInputChange,
    handleMoveSelected,
    handleRenameGroup,
    handleUndoDelete,
    handleUrlIndex,
    startFileDrag,
  };
}

export { useFilesViewActions };
