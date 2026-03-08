import { FilesView } from "../components/FilesView";
import { HelpView } from "../components/HelpView";
import { ResourcesView } from "../components/ResourcesView";
import { SettingsView } from "../components/SettingsView";
import type { WorkspaceOverlayTab } from "../components/WorkspaceOverlayModal";
import type { useFileLibrary } from "./useFileLibrary";

type WorkspaceModalTab = WorkspaceOverlayTab;
type WorkspaceFileLibraryView = ReturnType<typeof useFileLibrary>;

function isWorkspaceModalTab(value: string): value is WorkspaceModalTab {
  return value === "Files" || value === "Resources" || value === "Settings" || value === "Help";
}

function hasHttpUrl(value: unknown): boolean {
  const text = String(value || "").trim();
  return /^https?:\/\//i.test(text);
}

function webSummaryHasUrl(value: unknown): boolean {
  if (!value || typeof value !== "object") {
    return false;
  }
  const summary = value as {
    evidence?: {
      top_sources?: Array<{ url?: unknown }>;
      items?: Array<{ url?: unknown; evidence?: Array<{ url?: unknown }> }>;
    };
  };
  const topSources = Array.isArray(summary.evidence?.top_sources) ? summary.evidence?.top_sources : [];
  for (const row of topSources) {
    if (hasHttpUrl(row?.url)) {
      return true;
    }
  }
  const items = Array.isArray(summary.evidence?.items) ? summary.evidence?.items : [];
  for (const item of items) {
    if (hasHttpUrl(item?.url)) {
      return true;
    }
    const nested = Array.isArray(item?.evidence) ? item.evidence : [];
    for (const entry of nested) {
      if (hasHttpUrl(entry?.url)) {
        return true;
      }
    }
  }
  return false;
}

function renderWorkspaceTabContent(tab: WorkspaceModalTab, fileLibrary: WorkspaceFileLibraryView) {
  if (tab === "Files") {
    return (
      <FilesView
        citationFocus={null}
        indexId={fileLibrary.defaultIndexId}
        files={fileLibrary.indexedFiles}
        fileGroups={fileLibrary.fileGroups}
        onRefreshFiles={fileLibrary.refreshFileCount}
        onUploadFiles={fileLibrary.handleUploadFiles}
        onCreateFileIngestionJob={fileLibrary.handleCreateFileIngestionJob}
        onCancelFileUpload={fileLibrary.handleCancelFileUpload}
        onUploadUrls={fileLibrary.handleUploadUrlsToLibrary}
        onDeleteFiles={fileLibrary.handleDeleteFiles}
        onMoveFilesToGroup={fileLibrary.handleMoveFilesToGroup}
        onCreateFileGroup={fileLibrary.handleCreateFileGroup}
        onRenameFileGroup={fileLibrary.handleRenameFileGroup}
        onDeleteFileGroup={fileLibrary.handleDeleteFileGroup}
        ingestionJobs={fileLibrary.ingestionJobs}
        onRefreshIngestionJobs={fileLibrary.refreshIngestionJobs}
        uploadStatus={fileLibrary.uploadStatus}
        uploadProgressPercent={fileLibrary.uploadProgressPercent}
        uploadProgressLabel={fileLibrary.uploadProgressLabel}
        isCancelingUpload={fileLibrary.isCancelingUpload}
      />
    );
  }
  if (tab === "Resources") {
    return <ResourcesView />;
  }
  if (tab === "Settings") {
    return <SettingsView />;
  }
  return <HelpView />;
}

export { hasHttpUrl, isWorkspaceModalTab, renderWorkspaceTabContent, webSummaryHasUrl };
export type { WorkspaceModalTab };
