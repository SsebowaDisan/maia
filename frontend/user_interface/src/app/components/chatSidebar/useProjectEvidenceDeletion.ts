import { useCallback, type Dispatch, type SetStateAction } from "react";

import { deleteFiles, deleteUrls } from "../../../api/client";
import { normalizeSourceUrl, type ProjectEvidenceItem, type ProjectSourceBinding } from "./projectEvidenceHelpers";
import type { DeletePromptArgs } from "./useDeletePromptController";

type UseProjectEvidenceDeletionArgs = {
  canManageSources: boolean;
  evidenceProjectId: string;
  getEvidenceDisplayLabel: (item: ProjectEvidenceItem) => string;
  openDeletePrompt: (args: DeletePromptArgs) => void;
  setEvidenceActionBusyByKey: Dispatch<SetStateAction<Record<string, boolean>>>;
  setProjectUploadStatus: (projectId: string, message: string) => void;
  setSourceAliases: Dispatch<SetStateAction<Record<string, string>>>;
  setProjectSourceBindings: Dispatch<SetStateAction<Record<string, ProjectSourceBinding>>>;
  loadProjectEvidence: (projectId: string) => Promise<void>;
};

export function useProjectEvidenceDeletion({
  canManageSources,
  evidenceProjectId,
  getEvidenceDisplayLabel,
  openDeletePrompt,
  setEvidenceActionBusyByKey,
  setProjectUploadStatus,
  setSourceAliases,
  setProjectSourceBindings,
  loadProjectEvidence,
}: UseProjectEvidenceDeletionArgs) {
  const handleDeleteEvidenceItem = useCallback(
    (item: ProjectEvidenceItem) => {
      if (!evidenceProjectId) {
        return;
      }
      if (!canManageSources) {
        setProjectUploadStatus(
          evidenceProjectId,
          "Only workspace admins can delete indexed sources.",
        );
        return;
      }
      const fileIds = Array.from(new Set((item.fileIds || []).filter(Boolean)));
      const fallbackUrl = String(item.href || item.label || "").trim();
      const canDeleteViaUrl = item.type === "url" && Boolean(fallbackUrl);
      if (!fileIds.length && !canDeleteViaUrl) {
        setProjectUploadStatus(
          evidenceProjectId,
          `Delete unavailable for "${getEvidenceDisplayLabel(item)}".`,
        );
        return;
      }

      const label = getEvidenceDisplayLabel(item);
      openDeletePrompt({
        title: "Delete source",
        description: `Type delete to remove "${label}" from indexed sources.`,
        confirmLabel: "Delete source",
        action: async () => {
          setEvidenceActionBusyByKey((prev) => ({ ...prev, [item.key]: true }));
          try {
            if (fileIds.length) {
              const response = await deleteFiles(fileIds);
              const deletedCount = response.deleted_ids.length;
              const failedCount = response.failed.length;
              setProjectUploadStatus(
                evidenceProjectId,
                failedCount > 0
                  ? `Deleted ${deletedCount} source(s), ${failedCount} failed.`
                  : `Deleted ${deletedCount} source(s).`,
              );
            } else {
              const response = await deleteUrls([fallbackUrl]);
              const deletedCount = response.deleted_ids.length;
              const failedCount = response.failed.length;
              if (deletedCount > 0) {
                setProjectUploadStatus(
                  evidenceProjectId,
                  failedCount > 0
                    ? `Deleted ${deletedCount} source(s), ${failedCount} URL(s) failed.`
                    : `Deleted ${deletedCount} source(s) from URL.`,
                );
              } else {
                const firstFailure = response.failed[0];
                setProjectUploadStatus(
                  evidenceProjectId,
                  firstFailure?.message || "No indexed source matched this URL.",
                );
              }
            }
            setSourceAliases((prev) => {
              if (!Object.prototype.hasOwnProperty.call(prev, item.key)) {
                return prev;
              }
              const next = { ...prev };
              delete next[item.key];
              return next;
            });
            setProjectSourceBindings((prev) => {
              const current = prev[evidenceProjectId];
              if (!current) {
                return prev;
              }
              const itemFileIds = new Set((item.fileIds || []).map((value) => String(value || "").trim()).filter(Boolean));
              const normalizedUrl = normalizeSourceUrl(String(item.href || item.label || ""));
              const nextFileIds = current.fileIds.filter((value) => !itemFileIds.has(String(value || "").trim()));
              const nextUrls = normalizedUrl
                ? current.urls.filter((value) => normalizeSourceUrl(String(value || "")) !== normalizedUrl)
                : current.urls;
              if (
                nextFileIds.length === current.fileIds.length &&
                nextUrls.length === current.urls.length
              ) {
                return prev;
              }
              return {
                ...prev,
                [evidenceProjectId]: {
                  fileIds: nextFileIds,
                  urls: nextUrls,
                },
              };
            });
            await loadProjectEvidence(evidenceProjectId);
          } catch (error) {
            setProjectUploadStatus(
              evidenceProjectId,
              `Delete failed for "${label}": ${String(error)}`,
            );
            throw error;
          } finally {
            setEvidenceActionBusyByKey((prev) => ({ ...prev, [item.key]: false }));
          }
        },
      });
    },
    [
      canManageSources,
      evidenceProjectId,
      getEvidenceDisplayLabel,
      loadProjectEvidence,
      openDeletePrompt,
      setEvidenceActionBusyByKey,
      setProjectSourceBindings,
      setProjectUploadStatus,
      setSourceAliases,
    ],
  );

  return { handleDeleteEvidenceItem };
}
