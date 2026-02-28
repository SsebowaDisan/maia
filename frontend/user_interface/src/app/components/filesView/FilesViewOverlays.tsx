import { Eye, FolderPlus, HelpCircle, Trash2, X } from "lucide-react";
import type { FileGroupRecord } from "../../../api/client";
import { NeutralSelect } from "./NeutralSelect";
import type { DeleteConfirmationState } from "./types";

interface FilesViewOverlaysProps {
  showCreateGroupModal: boolean;
  setShowCreateGroupModal: (value: boolean) => void;
  quickGroupName: string;
  setQuickGroupName: (value: string) => void;
  handleCreateQuickGroup: () => Promise<void>;
  isCreatingGroup: boolean;
  canCreateGroup: boolean;
  hasSelection: boolean;
  selectedCount: number;
  focusPdfPreview: () => void;
  selectedPdfPreviewUrl: string | null;
  targetGroupId: string;
  setTargetGroupId: (value: string) => void;
  hasGroups: boolean;
  fileGroups: FileGroupRecord[];
  handleMoveSelected: () => Promise<void>;
  isMovingSelection: boolean;
  canMoveSelection: boolean;
  clearSelection: () => void;
  handleDeleteSelected: () => void;
  isDeletingSelection: boolean;
  canDeleteFiles: boolean;
  pendingDeleteSeconds: number;
  pendingDeleteActive: boolean;
  deleteConfirmation: DeleteConfirmationState | null;
  deleteConfirmText: string;
  setDeleteConfirmText: (value: string) => void;
  handleCancelDeleteConfirmation: () => void;
  handleConfirmDeleteAfterTyping: () => void;
}

function FilesViewOverlays({
  showCreateGroupModal,
  setShowCreateGroupModal,
  quickGroupName,
  setQuickGroupName,
  handleCreateQuickGroup,
  isCreatingGroup,
  canCreateGroup,
  hasSelection,
  selectedCount,
  focusPdfPreview,
  selectedPdfPreviewUrl,
  targetGroupId,
  setTargetGroupId,
  hasGroups,
  fileGroups,
  handleMoveSelected,
  isMovingSelection,
  canMoveSelection,
  clearSelection,
  handleDeleteSelected,
  isDeletingSelection,
  canDeleteFiles,
  pendingDeleteSeconds,
  pendingDeleteActive,
  deleteConfirmation,
  deleteConfirmText,
  setDeleteConfirmText,
  handleCancelDeleteConfirmation,
  handleConfirmDeleteAfterTyping,
}: FilesViewOverlaysProps) {
  return (
    <>
      {showCreateGroupModal ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/25 px-4">
          <div className="w-full max-w-[460px] rounded-2xl border border-black/[0.08] bg-white p-5 shadow-[0_20px_48px_rgba(0,0,0,0.2)]">
            <p className="text-[20px] font-semibold tracking-tight text-[#1d1d1f]">New Group</p>
            <input
              value={quickGroupName}
              onChange={(event) => setQuickGroupName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void handleCreateQuickGroup();
                }
              }}
              placeholder="Group name"
              className="mt-4 h-11 w-full rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
              autoFocus
            />
            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                onClick={() => {
                  setShowCreateGroupModal(false);
                  setQuickGroupName("");
                }}
                className="h-10 rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] text-[#1d1d1f] hover:bg-[#f8f8fa]"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleCreateQuickGroup()}
                disabled={isCreatingGroup || !canCreateGroup || !quickGroupName.trim()}
                className="h-10 rounded-xl bg-[#1d1d1f] px-3 text-[13px] text-white hover:bg-[#2c2c30] disabled:opacity-45"
              >
                {isCreatingGroup ? "Creating..." : "Create Group"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {hasSelection ? (
        <div className="fixed bottom-6 left-1/2 z-30 w-full max-w-[880px] -translate-x-1/2 px-4">
          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-black/[0.08] bg-white/90 px-3 py-3 shadow-[0_14px_36px_rgba(0,0,0,0.14)] backdrop-blur">
            <span className="px-2 text-[13px] font-medium text-[#1d1d1f]">{selectedCount} selected</span>
            <button
              onClick={focusPdfPreview}
              disabled={!selectedPdfPreviewUrl}
              className="inline-flex h-9 items-center gap-1 rounded-lg border border-black/[0.08] bg-white px-2.5 text-[12px] text-[#1d1d1f] disabled:opacity-45"
            >
              <Eye className="h-3.5 w-3.5" />
              Preview
            </button>
            <NeutralSelect
              value={targetGroupId}
              placeholder="Move to group"
              disabled={!hasGroups}
              options={[
                { value: "", label: "Move to group" },
                ...fileGroups.map((group) => ({ value: group.id, label: group.name })),
              ]}
              onChange={setTargetGroupId}
              buttonClassName="h-9 min-w-[220px] rounded-lg border border-black/[0.08] bg-white px-3 text-[12px] text-[#1d1d1f]"
            />
            <button
              onClick={() => void handleMoveSelected()}
              disabled={isMovingSelection || !canMoveSelection || !targetGroupId}
              className="inline-flex h-9 items-center gap-1 rounded-lg border border-black/[0.08] bg-white px-2.5 text-[12px] text-[#1d1d1f] hover:bg-[#f8f8fa] disabled:opacity-45"
            >
              <FolderPlus className="h-3.5 w-3.5" />
              {isMovingSelection ? "Moving..." : "Move"}
            </button>
            <button
              onClick={clearSelection}
              className="inline-flex h-9 items-center gap-1 rounded-lg border border-black/[0.08] bg-white px-2.5 text-[12px] text-[#1d1d1f] hover:bg-[#f8f8fa]"
            >
              <X className="h-3.5 w-3.5" />
              Clear
            </button>
            <button
              onClick={handleDeleteSelected}
              disabled={isDeletingSelection || !canDeleteFiles || pendingDeleteActive}
              className="inline-flex h-9 items-center gap-1 rounded-lg border border-[#ffd3d6] bg-white px-2.5 text-[12px] text-[#b42318] disabled:opacity-45"
            >
              <Trash2 className="h-3.5 w-3.5" />
              {isDeletingSelection ? "Deleting..." : pendingDeleteActive ? `Queued (${pendingDeleteSeconds}s)` : "Delete"}
            </button>
          </div>
        </div>
      ) : null}

      {deleteConfirmation ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/35 px-4">
          <div className="w-full max-w-[520px] rounded-2xl border border-black/[0.08] bg-white p-5 shadow-[0_18px_52px_rgba(0,0,0,0.2)]">
            <p className="text-[18px] font-semibold tracking-tight text-[#1d1d1f]">Confirm file deletion</p>
            <p className="mt-2 text-[13px] text-[#4b4b50]">
              Type <span className="font-semibold text-[#1d1d1f]">delete</span> to remove{" "}
              {deleteConfirmation.count === 1
                ? `"${deleteConfirmation.primaryName}"`
                : `${deleteConfirmation.count} selected files`}
              .
            </p>
            <input
              value={deleteConfirmText}
              onChange={(event) => setDeleteConfirmText(event.target.value)}
              placeholder='Type "delete" to confirm'
              className="mt-4 h-10 w-full rounded-xl border border-black/[0.12] bg-white px-3 text-[13px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
              autoFocus
            />
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                onClick={handleCancelDeleteConfirmation}
                className="h-9 rounded-lg border border-black/[0.08] bg-white px-3 text-[12px] text-[#1d1d1f] hover:bg-[#f8f8fa]"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDeleteAfterTyping}
                disabled={deleteConfirmText.trim().toLowerCase() !== "delete"}
                className="h-9 rounded-lg border border-[#ffd3d6] bg-[#fff5f5] px-3 text-[12px] text-[#b42318] disabled:opacity-45"
              >
                Delete Files
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <button className="fixed bottom-6 right-6 flex h-9 w-9 items-center justify-center rounded-full border border-black/[0.08] bg-white text-[#86868b] shadow-sm hover:text-[#1d1d1f]">
        <HelpCircle className="h-5 w-5" />
      </button>
    </>
  );
}

export { FilesViewOverlays };
