import { useCallback, type Dispatch, type SetStateAction } from "react";

import { uploadFiles, uploadUrls } from "../../../api/client";
import { normalizeUrlDraftList } from "./projectEvidenceHelpers";

type UseProjectEvidenceUploadsArgs = {
  appendProjectSourceBindings: (projectId: string, payload: { fileIds?: string[]; urls?: string[] }) => void;
  loadProjectEvidence: (projectId: string) => Promise<void>;
  setProjectUploadBusy: (projectId: string, isBusy: boolean) => void;
  setProjectUploadStatus: (projectId: string, message: string) => void;
  projectUrlDraftById: Record<string, string>;
  setProjectUrlDraftById: Dispatch<SetStateAction<Record<string, string>>>;
};

export function useProjectEvidenceUploads({
  appendProjectSourceBindings,
  loadProjectEvidence,
  setProjectUploadBusy,
  setProjectUploadStatus,
  projectUrlDraftById,
  setProjectUrlDraftById,
}: UseProjectEvidenceUploadsArgs) {
  const handleProjectFileUpload = useCallback(
    async (projectId: string, files: FileList | null) => {
      if (!files || files.length <= 0) {
        return;
      }
      setProjectUploadBusy(projectId, true);
      setProjectUploadStatus(projectId, "Uploading files...");
      try {
        const response = await uploadFiles(files, {
          scope: "persistent",
          reindex: true,
        });
        const uploadedFileIds = response.items
          .filter((item) => item.status === "success")
          .map((item) => String(item.file_id || "").trim())
          .filter(Boolean);
        if (uploadedFileIds.length > 0) {
          appendProjectSourceBindings(projectId, {
            fileIds: uploadedFileIds,
          });
        }
        const successCount = response.items.filter((item) => item.status === "success").length;
        const failureCount = response.items.length - successCount;
        setProjectUploadStatus(
          projectId,
          failureCount > 0
            ? `Uploaded ${successCount} file(s), ${failureCount} failed.`
            : `Uploaded ${successCount} file(s).`,
        );
        await loadProjectEvidence(projectId);
      } catch (error) {
        setProjectUploadStatus(projectId, `File upload failed: ${String(error)}`);
      } finally {
        setProjectUploadBusy(projectId, false);
      }
    },
    [appendProjectSourceBindings, loadProjectEvidence, setProjectUploadBusy, setProjectUploadStatus],
  );

  const submitProjectUrls = useCallback(
    async (projectId: string) => {
      const draft = String(projectUrlDraftById[projectId] || "").trim();
      if (!draft) {
        return;
      }
      setProjectUploadBusy(projectId, true);
      setProjectUploadStatus(projectId, "Indexing URLs...");
      try {
        const normalizedUrls = normalizeUrlDraftList(draft);
        const response = await uploadUrls(draft, {
          reindex: false,
          web_crawl_depth: 0,
          web_crawl_max_pages: 0,
          web_crawl_same_domain_only: true,
          include_pdfs: true,
          include_images: true,
        });
        const indexedFileIds = response.items
          .filter((item) => item.status === "success")
          .map((item) => String(item.file_id || "").trim())
          .filter(Boolean);
        if (normalizedUrls.length > 0 || indexedFileIds.length > 0) {
          appendProjectSourceBindings(projectId, {
            urls: normalizedUrls,
            fileIds: indexedFileIds,
          });
        }
        const successCount = response.items.filter((item) => item.status === "success").length;
        const failureCount = response.items.length - successCount;
        setProjectUploadStatus(
          projectId,
          failureCount > 0
            ? `Indexed ${successCount} URL source(s), ${failureCount} failed.`
            : `Indexed ${successCount} URL source(s).`,
        );
        setProjectUrlDraftById((prev) => ({
          ...prev,
          [projectId]: "",
        }));
        await loadProjectEvidence(projectId);
      } catch (error) {
        setProjectUploadStatus(projectId, `URL indexing failed: ${String(error)}`);
      } finally {
        setProjectUploadBusy(projectId, false);
      }
    },
    [
      appendProjectSourceBindings,
      loadProjectEvidence,
      projectUrlDraftById,
      setProjectUploadBusy,
      setProjectUploadStatus,
      setProjectUrlDraftById,
    ],
  );

  return {
    handleProjectFileUpload,
    submitProjectUrls,
  };
}
