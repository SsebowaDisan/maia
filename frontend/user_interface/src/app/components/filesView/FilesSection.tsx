import type { DragEvent } from "react";
import { ArrowUpDown, CheckSquare, LayoutGrid, List, Search, Square } from "lucide-react";
import type { FileRecord } from "../../../api/client";
import { formatDate, formatSize, loaderText, readinessLabel, readinessTone, tokenText } from "./helpers";
import { NeutralSelect } from "./NeutralSelect";
import type { FileKind, GridMode, SortField } from "./types";

interface FilesSectionProps {
  filterText: string;
  setFilterText: (value: string) => void;
  sortField: SortField;
  setSortField: (value: SortField) => void;
  sortDir: "asc" | "desc";
  setSortDir: (value: "asc" | "desc") => void;
  kindFilter: FileKind;
  setKindFilter: (value: FileKind) => void;
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
  onOpenFilePreview: (fileId: string) => void;
}

function FilesSection({
  filterText,
  setFilterText,
  sortField,
  setSortField,
  sortDir,
  setSortDir,
  kindFilter,
  setKindFilter,
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
  onOpenFilePreview,
}: FilesSectionProps) {
  const readinessClasses = (file: FileRecord) => {
    const tone = readinessTone(file.note || {}, file);
    if (tone === "ready") {
      return "border-[#2f8f3e]/20 bg-[#eefaf0] text-[#1f7a32]";
    }
    if (tone === "warning") {
      return "border-[#d5a54b]/24 bg-[#fff8e8] text-[#8a5a00]";
    }
    return "border-black/[0.08] bg-[#f6f6f8] text-[#6e6e73]";
  };

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

      <div className="mt-5 flex flex-wrap items-center gap-3">
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

      {viewMode === "table" ? (
        <div className="mt-8 overflow-hidden rounded-2xl border border-black/[0.06] bg-white">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] xl:min-w-[980px]">
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
                  <th className="min-w-[168px] px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93]">Status</th>
                  <th className="hidden px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93] 2xl:table-cell">Groups</th>
                  <th className="hidden px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-[#8d8d93] 2xl:table-cell">Date Created</th>
                </tr>
              </thead>
              <tbody>
                {visibleFiles.length === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-[13px] text-[#8d8d93]" colSpan={8}>
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
                        onClick={(event) => {
                          if (event.detail > 1) return;
                          toggleFileSelection(file.id);
                        }}
                        onDoubleClick={() => onOpenFilePreview(file.id)}
                        className={`cursor-pointer border-t border-[#f2f2f5] transition-colors ${
                          isSelected ? "bg-[#f7f7f9]" : "hover:bg-[#fbfbfd]"
                        } ${draggingFileId === file.id ? "opacity-65" : ""}`}
                      >
                        <td className="px-3 py-4">
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
                        <td className="max-w-[360px] truncate px-4 py-4 text-[14px] text-[#1d1d1f]">{file.name}</td>
                        <td className="whitespace-nowrap px-4 py-4 text-[14px] text-[#1d1d1f]">{formatSize(file.size)}</td>
                        <td className="whitespace-nowrap px-4 py-4 text-[14px] text-[#1d1d1f]">{tokenText(file.note || {})}</td>
                        <td className="max-w-[240px] truncate whitespace-nowrap px-4 py-4 text-[14px] text-[#1d1d1f]">{loaderText(file.note || {})}</td>
                        <td className="min-w-[168px] px-4 py-4">
                          <span
                            className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-medium ${readinessClasses(file)}`}
                          >
                            <span className="h-1.5 w-1.5 rounded-full bg-current/70" />
                            {readinessLabel(file.note || {}, file)}
                          </span>
                        </td>
                        <td className="hidden max-w-[260px] truncate px-4 py-4 text-[13px] text-[#6e6e73] 2xl:table-cell">
                          {groupsByFileId.get(file.id)?.length ? groupsByFileId.get(file.id)!.join(", ") : "-"}
                        </td>
                        <td className="hidden whitespace-nowrap px-4 py-4 text-[13px] text-[#6e6e73] 2xl:table-cell">{formatDate(file.date_created)}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
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
                  onClick={(event) => {
                    if (event.detail > 1) return;
                    toggleFileSelection(file.id);
                  }}
                  onDoubleClick={() => onOpenFilePreview(file.id)}
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
                  <p className="mt-2">
                    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] ${readinessClasses(file)}`}>
                      <span className="h-1.5 w-1.5 rounded-full bg-current/70" />
                      {readinessLabel(file.note || {}, file)}
                    </span>
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
