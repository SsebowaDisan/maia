import type { DragEvent } from "react";
import { CheckSquare, LayoutGrid, List, Square } from "lucide-react";
import type { FileRecord } from "../../../api/client";
import { formatDate, formatSize, loaderText, tokenText } from "./helpers";
import type { GridMode } from "./types";

interface FilesSectionProps {
  viewMode: GridMode;
  setViewMode: (mode: GridMode) => void;
  visibleFiles: FileRecord[];
  selectedFileIds: string[];
  toggleSelectAllVisible: () => void;
  areAllVisibleSelected: boolean;
  toggleFileSelection: (fileId: string) => void;
  draggingFileId: string | null;
  canMoveFiles: boolean;
  startFileDrag: (event: DragEvent<HTMLElement>, fileId: string) => void;
  endFileDrag: () => void;
  groupsByFileId: Map<string, string[]>;
}

function FilesSection({
  viewMode,
  setViewMode,
  visibleFiles,
  selectedFileIds,
  toggleSelectAllVisible,
  areAllVisibleSelected,
  toggleFileSelection,
  draggingFileId,
  canMoveFiles,
  startFileDrag,
  endFileDrag,
  groupsByFileId,
}: FilesSectionProps) {
  return (
    <>
      <div className="mt-8 flex items-center justify-between">
        <p className="text-[20px] font-semibold tracking-tight text-[#1d1d1f]">Files</p>
        <div className="flex items-center gap-3">
          <span className="text-[12px] text-[#8d8d93]">{visibleFiles.length} visible</span>
          <div className="inline-flex items-center gap-1 rounded-xl border border-black/[0.08] bg-white p-1">
            <button
              onClick={() => setViewMode("table")}
              className={`inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-[12px] ${
                viewMode === "table" ? "bg-[#f3f3f6] font-semibold text-[#1d1d1f]" : "text-[#8d8d93]"
              }`}
              title="File table view"
            >
              <List className="h-3.5 w-3.5" />
              Table
            </button>
            <button
              onClick={() => setViewMode("cards")}
              className={`inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-[12px] ${
                viewMode === "cards" ? "bg-[#f3f3f6] font-semibold text-[#1d1d1f]" : "text-[#8d8d93]"
              }`}
              title="File card view"
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              Cards
            </button>
          </div>
        </div>
      </div>

      {viewMode === "table" ? (
        <div className="mt-8 overflow-hidden rounded-2xl border border-black/[0.06]">
          <table className="w-full">
            <thead className="border-b border-[#f2f2f5] bg-[#fcfcfd]">
              <tr>
                <th className="w-[52px] px-3 py-3 text-left">
                  <button
                    onClick={toggleSelectAllVisible}
                    className="rounded-md p-1 text-[#8d8d93] hover:text-[#1d1d1f]"
                    aria-label={areAllVisibleSelected ? "Unselect visible files" : "Select visible files"}
                  >
                    {areAllVisibleSelected ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4" />}
                  </button>
                </th>
                <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93]">Name</th>
                <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93]">Size</th>
                <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93]">Token</th>
                <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93]">Loader</th>
                <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93]">Groups</th>
                <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93]">Date Created</th>
              </tr>
            </thead>
            <tbody>
              {visibleFiles.length === 0 ? (
                <tr>
                  <td className="px-4 py-8 text-[13px] text-[#8d8d93]" colSpan={7}>
                    No indexed files found.
                  </td>
                </tr>
              ) : (
                visibleFiles.map((file) => {
                  const isSelected = selectedFileIds.includes(file.id);
                  return (
                    <tr
                      key={file.id}
                      draggable={canMoveFiles}
                      onDragStart={(event) => startFileDrag(event, file.id)}
                      onDragEnd={endFileDrag}
                      onClick={() => toggleFileSelection(file.id)}
                      className={`cursor-pointer border-t border-[#f2f2f5] ${
                        isSelected ? "bg-[#f7f7f9]" : "hover:bg-[#fbfbfd]"
                      } ${draggingFileId === file.id ? "opacity-65" : ""}`}
                    >
                      <td className="px-3 py-5">
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            toggleFileSelection(file.id);
                          }}
                          className="rounded-md p-1 text-[#8d8d93] hover:text-[#1d1d1f]"
                          aria-label={isSelected ? `Unselect ${file.name}` : `Select ${file.name}`}
                        >
                          {isSelected ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4" />}
                        </button>
                      </td>
                      <td className="max-w-[340px] truncate px-4 py-5 text-[14px] text-[#1d1d1f]">{file.name}</td>
                      <td className="px-4 py-5 text-[14px] text-[#1d1d1f]">{formatSize(file.size)}</td>
                      <td className="px-4 py-5 text-[14px] text-[#1d1d1f]">{tokenText(file.note || {})}</td>
                      <td className="px-4 py-5 text-[14px] text-[#1d1d1f]">{loaderText(file.note || {})}</td>
                      <td className="max-w-[260px] truncate px-4 py-5 text-[13px] text-[#6e6e73]">
                        {groupsByFileId.get(file.id)?.length ? groupsByFileId.get(file.id)!.join(", ") : "-"}
                      </td>
                      <td className="px-4 py-5 text-[13px] text-[#6e6e73]">{formatDate(file.date_created)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visibleFiles.length === 0 ? (
            <div className="rounded-xl border border-black/[0.08] bg-white px-3 py-4 text-[13px] text-[#8d8d93]">
              No indexed files found.
            </div>
          ) : (
            visibleFiles.map((file) => {
              const isSelected = selectedFileIds.includes(file.id);
              return (
                <button
                  key={file.id}
                  draggable={canMoveFiles}
                  onDragStart={(event) => startFileDrag(event, file.id)}
                  onDragEnd={endFileDrag}
                  onClick={() => toggleFileSelection(file.id)}
                  className={`rounded-xl border px-4 py-4 text-left ${
                    isSelected ? "border-[#1d1d1f] bg-[#f7f7f9]" : "border-black/[0.08] bg-white"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {isSelected ? <CheckSquare className="h-4 w-4 text-[#1d1d1f]" /> : <Square className="h-4 w-4 text-[#8d8d93]" />}
                    <p className="truncate text-[14px] font-medium text-[#1d1d1f]">{file.name}</p>
                  </div>
                  <p className="mt-1 text-[12px] text-[#6e6e73]">
                    {formatSize(file.size)} | {loaderText(file.note || {})}
                  </p>
                  <p className="mt-1 truncate text-[11px] text-[#8d8d93]">
                    {groupsByFileId.get(file.id)?.length ? groupsByFileId.get(file.id)!.join(", ") : "No group"}
                  </p>
                </button>
              );
            })
          )}
        </div>
      )}
    </>
  );
}

export { FilesSection };
