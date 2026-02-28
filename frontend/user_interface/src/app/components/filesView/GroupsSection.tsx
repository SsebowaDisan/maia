import type { DragEvent } from "react";
import { Folder, FolderPlus, LayoutGrid, List } from "lucide-react";
import type { FileGroupRecord } from "../../../api/client";
import type { GridMode, GroupRow } from "./types";

interface GroupsSectionProps {
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
}

function handleGroupDragOver(
  event: DragEvent<HTMLElement>,
  groupId: string,
  droppable: boolean,
  canMoveFiles: boolean,
  setDragOverGroupId: (groupId: string | null) => void,
) {
  if (!droppable || !canMoveFiles) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
  setDragOverGroupId(groupId);
}

function GroupsSection({
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
}: GroupsSectionProps) {
  return (
    <div className="mt-8">
      <div className="flex items-center justify-between">
        <p className="text-[20px] font-semibold tracking-tight text-[#1d1d1f]">Groups</p>
        <div className="flex items-center gap-3">
          <span className="text-[12px] text-[#8d8d93]">{groupSummaryCount} total</span>
          <div className="inline-flex items-center gap-1 rounded-xl border border-black/[0.08] bg-white p-1">
            <button
              onClick={() => setGroupViewMode("table")}
              className={`inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-[12px] ${
                groupViewMode === "table" ? "bg-[#f3f3f6] font-semibold text-[#1d1d1f]" : "text-[#8d8d93]"
              }`}
              title="Group table view"
            >
              <List className="h-3.5 w-3.5" />
              Table
            </button>
            <button
              onClick={() => setGroupViewMode("cards")}
              className={`inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-[12px] ${
                groupViewMode === "cards" ? "bg-[#f3f3f6] font-semibold text-[#1d1d1f]" : "text-[#8d8d93]"
              }`}
              title="Group card view"
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              Cards
            </button>
          </div>
          <button
            onClick={onCreateGroupModalOpen}
            disabled={!canCreateGroup}
            className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] text-[#1d1d1f] hover:bg-[#f8f8fa] disabled:opacity-45"
          >
            <FolderPlus className="h-3.5 w-3.5" />
            New Group
          </button>
        </div>
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl border border-black/[0.06]">
        {groupViewMode === "table" ? (
          <table className="w-full">
            <thead className="border-b border-[#f2f2f5] bg-[#fcfcfd]">
              <tr>
                <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93]">
                  Group
                </th>
                <th className="px-4 py-3 text-right text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93]">
                  Files
                </th>
              </tr>
            </thead>
            <tbody>
              {groupRows.map((group, index) => {
                const isActive = activeGroupFilter === group.id;
                const isDropTarget = group.droppable && dragOverGroupId === group.id;
                return (
                  <tr
                    key={group.id}
                    onClick={() => setActiveGroupFilter(group.id)}
                    onDragOver={(event) =>
                      handleGroupDragOver(event, group.id, group.droppable, canMoveFiles, setDragOverGroupId)
                    }
                    onDragLeave={() => {
                      if (dragOverGroupId === group.id) {
                        setDragOverGroupId(null);
                      }
                    }}
                    onDrop={(event) => {
                      if (!group.droppable || !canMoveFiles) return;
                      event.preventDefault();
                      const droppedId = event.dataTransfer.getData("text/plain") || draggingFileId || "";
                      setDragOverGroupId(null);
                      void onDropFilesIntoGroup(group.id, droppedId || null);
                    }}
                    className={`cursor-pointer ${index < groupRows.length - 1 ? "border-b border-[#f2f2f5]" : ""} ${
                      isActive || isDropTarget ? "bg-[#f7f7f9]" : "hover:bg-[#fafafd]"
                    }`}
                  >
                    <td className="px-4 py-[18px]">
                      <div className="inline-flex items-center gap-2">
                        <Folder className={`h-4 w-4 ${isActive ? "text-[#1d1d1f]" : "text-[#8d8d93]"}`} />
                        <span className="truncate pr-3 text-[15px] font-medium text-[#1d1d1f]">{group.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-[18px] text-right text-[13px] text-[#1d1d1f]/55">{group.count}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="grid grid-cols-1 gap-3 p-3 md:grid-cols-2 xl:grid-cols-3">
            {groupRows.map((group) => {
              const isActive = activeGroupFilter === group.id;
              const isDropTarget = group.droppable && dragOverGroupId === group.id;
              return (
                <button
                  key={`group-card-${group.id}`}
                  onClick={() => setActiveGroupFilter(group.id)}
                  onDragOver={(event) =>
                    handleGroupDragOver(event, group.id, group.droppable, canMoveFiles, setDragOverGroupId)
                  }
                  onDragLeave={() => {
                    if (dragOverGroupId === group.id) {
                      setDragOverGroupId(null);
                    }
                  }}
                  onDrop={(event) => {
                    if (!group.droppable || !canMoveFiles) return;
                    event.preventDefault();
                    const droppedId = event.dataTransfer.getData("text/plain") || draggingFileId || "";
                    setDragOverGroupId(null);
                    void onDropFilesIntoGroup(group.id, droppedId || null);
                  }}
                  className={`rounded-xl border p-4 text-left transition-colors ${
                    isActive || isDropTarget
                      ? "border-[#1d1d1f]/18 bg-[#f7f7f9]"
                      : "border-black/[0.08] bg-white hover:bg-[#fafafd]"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Folder className={`h-4 w-4 ${isActive ? "text-[#1d1d1f]" : "text-[#8d8d93]"}`} />
                    <p className="truncate text-[15px] font-medium text-[#1d1d1f]">{group.name}</p>
                  </div>
                  <p className="mt-1 text-[13px] text-[#1d1d1f]/55">{group.count} files</p>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {activeGroupRecord ? (
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <input
            value={manageGroupName}
            onChange={(event) => setManageGroupName(event.target.value)}
            placeholder="Rename group"
            className="h-11 min-w-[250px] flex-1 rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
          />
          <button
            onClick={() => void handleRenameGroup()}
            disabled={!canRenameGroup || isManagingGroup}
            className="h-11 rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] text-[#1d1d1f] hover:bg-[#f8f8fa] disabled:opacity-45"
          >
            Rename
          </button>
          <button
            onClick={() => void handleDeleteGroup()}
            disabled={!canDeleteGroup || isManagingGroup}
            className="h-11 rounded-xl border border-[#ffd3d6] bg-white px-3 text-[13px] text-[#b42318] disabled:opacity-45"
          >
            Delete
          </button>
        </div>
      ) : null}
    </div>
  );
}

export { GroupsSection };
