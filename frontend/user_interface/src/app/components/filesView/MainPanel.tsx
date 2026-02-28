import { ArrowUpDown, Search } from "lucide-react";
import type { CitationFocus } from "../../types";
import type { FileGroupRecord, FileRecord } from "../../../api/client";
import { GroupsSection } from "./GroupsSection";
import { FilesSection } from "./FilesSection";
import { NeutralSelect } from "./NeutralSelect";
import type { FileKind, GridMode, GroupRow, SortField } from "./types";

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
  citationFocus,
  citationRawUrl,
}: MainPanelProps) {
  return (
    <div className="min-w-0">
      <div className="rounded-[24px] border border-black/[0.06] bg-white px-6 py-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[280px] flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8d8d93]" />
            <input
              value={filterText}
              onChange={(event) => setFilterText(event.target.value)}
              placeholder="Search files"
              className="h-11 w-full rounded-xl border border-black/[0.08] bg-white pl-9 pr-3 text-[13px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
            />
          </div>
          <NeutralSelect
            value={sortField}
            placeholder="Sort"
            options={[
              { value: "date", label: "Sort: Date" },
              { value: "name", label: "Sort: Name" },
              { value: "size", label: "Sort: Size" },
              { value: "token", label: "Sort: Token" },
            ]}
            onChange={(nextValue) => setSortField(nextValue as SortField)}
            buttonClassName="h-11 min-w-[140px] rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] text-[#1d1d1f]"
          />
          <button
            onClick={() => setSortDir(sortDir === "asc" ? "desc" : "asc")}
            className="inline-flex h-11 items-center gap-1.5 rounded-xl border border-black/[0.08] px-3 text-[13px] text-[#1d1d1f]"
          >
            <ArrowUpDown className="h-4 w-4" />
            {sortDir === "asc" ? "Asc" : "Desc"}
          </button>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-5 border-b border-[#f2f2f5] pb-4">
          {(["all", "pdf", "office", "text", "image", "other"] as FileKind[]).map((kind) => (
            <button
              key={kind}
              onClick={() => setKindFilter(kind)}
              className={`rounded-md px-2 py-1 text-[12px] uppercase tracking-[0.04em] transition-colors ${
                kindFilter === kind ? "bg-[#f3f3f6] text-[#1d1d1f] font-semibold" : "text-[#8d8d93]"
              }`}
            >
              {kind}
            </button>
          ))}
        </div>

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
        />
      </div>

      {citationFocus && citationRawUrl ? (
        <div className="mt-6 rounded-2xl border border-black/[0.08] bg-white p-4">
          <p className="mb-2 text-[12px] text-[#6e6e73]">Citation source</p>
          <a href={citationRawUrl} target="_blank" rel="noopener noreferrer" className="text-[13px] text-[#2f2f34] hover:underline">
            Open {citationFocus.sourceName}
          </a>
        </div>
      ) : null}
    </div>
  );
}

export { MainPanel };
