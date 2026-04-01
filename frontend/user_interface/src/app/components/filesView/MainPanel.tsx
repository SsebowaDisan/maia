import type { CitationFocus } from "../../types";
import type { FileGroupRecord, FileRecord } from "../../../api/client";
import { GroupsSection } from "./GroupsSection";
import { FilesSection } from "./FilesSection";
import type { FileKind, GridMode, GroupRow, SortField } from "./types";

function normalizeHttpUrl(rawValue: unknown): string {
  const value = String(rawValue || "").split(/\s+/).join(" ").trim();
  if (!value) {
    return "";
  }
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return "";
    }
    return parsed.toString();
  } catch {
    return "";
  }
}

interface MainPanelProps {
  filterText: string;
  setFilterText: (value: string) => void;
  sortField: SortField;
  setSortField: (value: SortField) => void;
  sortDir: "asc" | "desc";
  setSortDir: (value: "asc" | "desc") => void;
  kindFilter: FileKind;
  setKindFilter: (value: FileKind) => void;
  groupSummaryCount: number;
  groupViewMode: GridMode;
  setGroupViewMode: (mode: GridMode) => void;
  onCreateGroupModalOpen: () => void;
  canCreateGroup: boolean;
  groupRows: GroupRow[];
  activeGroupFilter: string;
  setActiveGroupFilter: (groupId: string) => void;
  dragOverGroupId: string | null;
  setDragOverGroupId: (groupId: string | null) => void;
  draggingFileId: string | null;
  canMoveFiles: boolean;
  onDropFilesIntoGroup: (groupId: string, sourceFileId: string | null) => Promise<void>;
  activeGroupRecord: FileGroupRecord | null;
  manageGroupName: string;
  setManageGroupName: (name: string) => void;
  handleRenameGroup: () => Promise<void>;
  handleDeleteGroup: () => Promise<void>;
  isManagingGroup: boolean;
  canRenameGroup: boolean;
  canDeleteGroup: boolean;
  pendingDelete: { count: number } | null;
  pendingDeleteSeconds: number;
  handleUndoDelete: () => void;
  handleDeleteNow: () => void;
  actionMessage: string;
  viewMode: GridMode;
  setViewMode: (mode: GridMode) => void;
  visibleFiles: FileRecord[];
  selectedFileIds: string[];
  toggleSelectAllVisible: () => void;
  areAllVisibleSelected: boolean;
  toggleFileSelection: (fileId: string) => void;
  startFileDrag: (event: React.DragEvent<HTMLElement>, fileId: string) => void;
  endFileDrag: () => void;
  groupsByFileId: Map<string, string[]>;
  onOpenFilePreview: (fileId: string) => void;
  citationFocus: CitationFocus | null;
  citationRawUrl: string | null;
}

function MainPanel({
  filterText,
  setFilterText,
  sortField,
  setSortField,
  sortDir,
  setSortDir,
  kindFilter,
  setKindFilter,
  groupSummaryCount,
  groupViewMode,
  setGroupViewMode,
  onCreateGroupModalOpen,
  canCreateGroup,
  groupRows,
  activeGroupFilter,
  setActiveGroupFilter,
  dragOverGroupId,
  setDragOverGroupId,
  draggingFileId,
  canMoveFiles,
  onDropFilesIntoGroup,
  activeGroupRecord,
  manageGroupName,
  setManageGroupName,
  handleRenameGroup,
  handleDeleteGroup,
  isManagingGroup,
  canRenameGroup,
  canDeleteGroup,
  pendingDelete,
  pendingDeleteSeconds,
  handleUndoDelete,
  handleDeleteNow,
  actionMessage,
  viewMode,
  setViewMode,
  visibleFiles,
  selectedFileIds,
  toggleSelectAllVisible,
  areAllVisibleSelected,
  toggleFileSelection,
  startFileDrag,
  endFileDrag,
  groupsByFileId,
  onOpenFilePreview,
  citationFocus,
  citationRawUrl,
}: MainPanelProps) {
  const citationWebsiteUrl = normalizeHttpUrl(citationFocus?.sourceUrl) || normalizeHttpUrl(citationFocus?.sourceName);
  const citationUsesWebsite = citationFocus?.sourceType === "website" || (Boolean(citationWebsiteUrl) && !citationRawUrl);
  const citationOpenUrl = citationUsesWebsite ? citationWebsiteUrl : citationRawUrl;

  return (
    <div className="min-w-0">
      <div className="rounded-[24px] border border-black/[0.06] bg-white px-6 py-6">
        <GroupsSection
          groupSummaryCount={groupSummaryCount}
          groupViewMode={groupViewMode}
          setGroupViewMode={setGroupViewMode}
          onCreateGroupModalOpen={onCreateGroupModalOpen}
          canCreateGroup={canCreateGroup}
          groupRows={groupRows}
          activeGroupFilter={activeGroupFilter}
          setActiveGroupFilter={setActiveGroupFilter}
          dragOverGroupId={dragOverGroupId}
          setDragOverGroupId={setDragOverGroupId}
          draggingFileId={draggingFileId}
          canMoveFiles={canMoveFiles}
          onDropFilesIntoGroup={onDropFilesIntoGroup}
          activeGroupRecord={activeGroupRecord}
          manageGroupName={manageGroupName}
          setManageGroupName={setManageGroupName}
          handleRenameGroup={handleRenameGroup}
          handleDeleteGroup={handleDeleteGroup}
          isManagingGroup={isManagingGroup}
          canRenameGroup={canRenameGroup}
          canDeleteGroup={canDeleteGroup}
        />

        {pendingDelete ? (
          <div className="mt-8 rounded-2xl border border-[#ffd8b4] bg-[#fff9f2] px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[12px] text-[#1d1d1f]">
                {pendingDelete.count} file(s) queued for deletion. Undo in {pendingDeleteSeconds}s.
              </p>
              <button
                onClick={handleUndoDelete}
                className="h-8 rounded-lg border border-black/[0.08] bg-white px-2.5 text-[12px] text-[#1d1d1f]"
              >
                Undo
              </button>
              <button
                onClick={handleDeleteNow}
                className="h-8 rounded-lg border border-[#ffd3d6] bg-white px-2.5 text-[12px] text-[#b42318]"
              >
                Delete now
              </button>
            </div>
          </div>
        ) : null}

        {actionMessage ? <p className="mt-6 text-[12px] text-[#6e6e73]">{actionMessage}</p> : null}

        <FilesSection
          filterText={filterText}
          setFilterText={setFilterText}
          sortField={sortField}
          setSortField={setSortField}
          sortDir={sortDir}
          setSortDir={setSortDir}
          kindFilter={kindFilter}
          setKindFilter={setKindFilter}
          viewMode={viewMode}
          setViewMode={setViewMode}
          visibleFiles={visibleFiles}
          selectedFileIds={selectedFileIds}
          toggleSelectAllVisible={toggleSelectAllVisible}
          areAllVisibleSelected={areAllVisibleSelected}
          toggleFileSelection={toggleFileSelection}
          draggingFileId={draggingFileId}
          canMoveFiles={canMoveFiles}
          startFileDrag={startFileDrag}
          endFileDrag={endFileDrag}
          groupsByFileId={groupsByFileId}
          onOpenFilePreview={onOpenFilePreview}
        />
      </div>

      {citationFocus && citationOpenUrl ? (
        <div className="mt-6 rounded-2xl border border-black/[0.08] bg-white p-4">
          <p className="mb-2 text-[12px] text-[#6e6e73]">Citation source</p>
          <a href={citationOpenUrl || undefined} target="_blank" rel="noopener noreferrer" className="text-[13px] text-[#2f2f34] hover:underline">
            Open {citationFocus.sourceName}
          </a>
        </div>
      ) : null}
    </div>
  );
}

export { MainPanel };
