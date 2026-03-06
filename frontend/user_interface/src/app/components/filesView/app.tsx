import { useEffect, useMemo, useRef, useState } from "react";
import { buildRawFileUrl } from "../../../api/client";
import { FilesViewOverlays } from "./FilesViewOverlays";
import { inferFileKind, tokenNumber, UNGROUPED_FILTER } from "./helpers";
import { MainPanel } from "./MainPanel";
import { PdfPreviewModal } from "./PdfPreviewModal";
import type { FileKind, FilesViewProps, GridMode, PendingDeleteJob, SortField, UploadTab } from "./types";
import { UploadSidebar } from "./UploadSidebar";
import { useFilesViewActions } from "./useFilesViewActions";

export function FilesView({
  citationFocus = null,
  indexId = null,
  files = [],
  fileGroups = [],
  onRefreshFiles,
  onUploadFiles,
  onCreateFileIngestionJob,
  onCancelFileUpload,
  onUploadUrls,
  onDeleteFiles,
  onMoveFilesToGroup,
  onCreateFileGroup,
  onRenameFileGroup,
  onDeleteFileGroup,
  ingestionJobs = [],
  onRefreshIngestionJobs,
  uploadStatus = "",
  uploadProgressPercent = null,
  uploadProgressLabel = "",
  isCancelingUpload = false,
}: FilesViewProps) {
  const [uploadTab, setUploadTab] = useState<UploadTab>("upload");
  const [filterText, setFilterText] = useState("");
  const [urlText, setUrlText] = useState("");
  const [forceReindex, setForceReindex] = useState(false);
  const [kindFilter, setKindFilter] = useState<FileKind>("all");
  const [sortField, setSortField] = useState<SortField>("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [viewMode, setViewMode] = useState<GridMode>("table");
  const [groupViewMode, setGroupViewMode] = useState<GridMode>("table");
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [targetGroupId, setTargetGroupId] = useState("");
  const [manageGroupId, setManageGroupId] = useState("");
  const [manageGroupName, setManageGroupName] = useState("");
  const [activeGroupFilter, setActiveGroupFilter] = useState("all");
  const [uploadGroupId, setUploadGroupId] = useState("");
  const [quickGroupName, setQuickGroupName] = useState("");
  const [showCreateGroupModal, setShowCreateGroupModal] = useState(false);
  const [draggingFileId, setDraggingFileId] = useState<string | null>(null);
  const [dragOverGroupId, setDragOverGroupId] = useState<string | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState<{
    fileIds: string[];
    count: number;
    primaryName: string;
  } | null>(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [pendingDelete, setPendingDelete] = useState<PendingDeleteJob | null>(null);
  const [deleteCountdownTick, setDeleteCountdownTick] = useState(0);
  const [isDeletingSelection, setIsDeletingSelection] = useState(false);
  const [isMovingSelection, setIsMovingSelection] = useState(false);
  const [isManagingGroup, setIsManagingGroup] = useState(false);
  const [isCreatingGroup, setIsCreatingGroup] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPdfPreviewModalOpen, setIsPdfPreviewModalOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const groupsByFileId = useMemo(() => {
    const map = new Map<string, string[]>();
    fileGroups.forEach((group) => {
      const cleanGroupName = (group.name || "").trim() || "Untitled Group";
      (group.file_ids || []).forEach((fileId) => {
        const current = map.get(fileId) || [];
        current.push(cleanGroupName);
        map.set(fileId, current);
      });
    });
    return map;
  }, [fileGroups]);

  const groupedFileIds = useMemo(() => {
    const ids = new Set<string>();
    fileGroups.forEach((group) => {
      (group.file_ids || []).forEach((fileId) => ids.add(fileId));
    });
    return ids;
  }, [fileGroups]);

  const visibleFiles = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    const activeGroup =
      activeGroupFilter === "all" || activeGroupFilter === UNGROUPED_FILTER
        ? null
        : fileGroups.find((group) => group.id === activeGroupFilter) || null;
    const activeGroupFileIds = activeGroup ? new Set(activeGroup.file_ids || []) : null;
    const base = files.filter((file) => {
      if (kindFilter !== "all" && inferFileKind(file.name) !== kindFilter) return false;
      if (activeGroupFilter === UNGROUPED_FILTER && groupedFileIds.has(file.id)) return false;
      if (activeGroupFileIds && !activeGroupFileIds.has(file.id)) return false;
      return !q || file.name.toLowerCase().includes(q);
    });
    const sorted = [...base].sort((a, b) => {
      if (sortField === "name") return a.name.localeCompare(b.name);
      if (sortField === "size") return a.size - b.size;
      if (sortField === "token") return tokenNumber(a.note || {}) - tokenNumber(b.note || {});
      return new Date(a.date_created).getTime() - new Date(b.date_created).getTime();
    });
    return sortDir === "desc" ? sorted.reverse() : sorted;
  }, [files, fileGroups, activeGroupFilter, filterText, kindFilter, sortDir, sortField, groupedFileIds]);

  const groupSummary = useMemo(() => {
    const existingIds = new Set(files.map((file) => file.id));
    return fileGroups.map((group) => {
      const count = (group.file_ids || []).filter((fileId) => existingIds.has(fileId)).length;
      return { ...group, count };
    });
  }, [fileGroups, files]);

  const selectedFiles = useMemo(() => {
    if (!selectedFileIds.length) return [];
    const selectedSet = new Set(selectedFileIds);
    return files.filter((file) => selectedSet.has(file.id));
  }, [files, selectedFileIds]);

  const selectedCount = selectedFiles.length;
  const hasSelection = selectedCount > 0;
  const hasGroups = groupSummary.length > 0;
  const activeGroupRecord = useMemo(
    () =>
      activeGroupFilter === "all" || activeGroupFilter === UNGROUPED_FILTER
        ? null
        : fileGroups.find((group) => group.id === activeGroupFilter) || null,
    [activeGroupFilter, fileGroups],
  );
  const ungroupedCount = useMemo(() => files.filter((file) => !groupedFileIds.has(file.id)).length, [files, groupedFileIds]);
  const groupRows = useMemo(
    () => [
      { id: "all", name: "All Files", count: files.length, droppable: false },
      { id: UNGROUPED_FILTER, name: "Ungrouped", count: ungroupedCount, droppable: false },
      ...groupSummary.map((group) => ({ id: group.id, name: group.name, count: group.count, droppable: true })),
    ],
    [files.length, ungroupedCount, groupSummary],
  );

  const selectedPdfFile = useMemo(() => selectedFiles.find((file) => inferFileKind(file.name) === "pdf") || null, [selectedFiles]);

  const selectedPdfPreviewUrl = useMemo(() => {
    if (!selectedPdfFile) return null;
    const raw = buildRawFileUrl(selectedPdfFile.id, { indexId: typeof indexId === "number" ? indexId : undefined });
    return `${raw}#view=FitH`;
  }, [selectedPdfFile, indexId]);

  const citationRawUrl = useMemo(() => {
    if (!citationFocus?.fileId) return null;
    return buildRawFileUrl(citationFocus.fileId, { indexId: typeof indexId === "number" ? indexId : undefined });
  }, [citationFocus, indexId]);

  useEffect(() => {
    if (!selectedPdfPreviewUrl && isPdfPreviewModalOpen) {
      setIsPdfPreviewModalOpen(false);
    }
  }, [selectedPdfPreviewUrl, isPdfPreviewModalOpen]);

  const recentJobs = useMemo(
    () =>
      [...ingestionJobs]
        .sort((a, b) => (a.date_created || "").localeCompare(b.date_created || ""))
        .reverse()
        .slice(0, 30),
    [ingestionJobs],
  );

  useEffect(() => {
    if (!selectedFileIds.length) return;
    const existing = new Set(files.map((file) => file.id));
    setSelectedFileIds((previous) => previous.filter((id) => existing.has(id)));
  }, [files, selectedFileIds.length]);

  useEffect(() => {
    if (!targetGroupId) return;
    if (!fileGroups.some((group) => group.id === targetGroupId)) {
      setTargetGroupId("");
    }
  }, [fileGroups, targetGroupId]);

  useEffect(() => {
    if (!manageGroupId) return;
    const group = fileGroups.find((item) => item.id === manageGroupId);
    if (!group) {
      setManageGroupId("");
      setManageGroupName("");
    }
  }, [fileGroups, manageGroupId]);

  useEffect(() => {
    if (activeGroupFilter === "all" || activeGroupFilter === UNGROUPED_FILTER) return;
    if (!fileGroups.some((group) => group.id === activeGroupFilter)) {
      setActiveGroupFilter("all");
    }
  }, [fileGroups, activeGroupFilter]);

  useEffect(() => {
    if (!activeGroupRecord) {
      setManageGroupId("");
      setManageGroupName("");
      return;
    }
    setManageGroupId(activeGroupRecord.id);
    setManageGroupName(activeGroupRecord.name || "");
    setTargetGroupId(activeGroupRecord.id);
  }, [activeGroupRecord]);

  useEffect(() => {
    if (!fileGroups.length) {
      setUploadGroupId("");
      return;
    }
    if (activeGroupRecord?.id) {
      setUploadGroupId(activeGroupRecord.id);
      return;
    }
    if (!uploadGroupId || !fileGroups.some((group) => group.id === uploadGroupId)) {
      setUploadGroupId(fileGroups[0].id);
    }
  }, [fileGroups, uploadGroupId, activeGroupRecord]);

  useEffect(() => {
    if (!pendingDelete) return;
    const intervalId = window.setInterval(() => {
      setDeleteCountdownTick((value) => value + 1);
    }, 250);
    return () => window.clearInterval(intervalId);
  }, [pendingDelete]);

  useEffect(() => {
    return () => {
      if (pendingDelete) {
        window.clearTimeout(pendingDelete.timeoutId);
      }
    };
  }, [pendingDelete]);

  useEffect(() => {
    if (!deleteConfirmation) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDeleteConfirmation(null);
        setDeleteConfirmText("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [deleteConfirmation]);

  const toggleFileSelection = (fileId: string) => {
    setSelectedFileIds((previous) => {
      if (previous.includes(fileId)) {
        return previous.filter((id) => id !== fileId);
      }
      return [...previous, fileId];
    });
  };

  const areAllVisibleSelected =
    visibleFiles.length > 0 && visibleFiles.every((file) => selectedFileIds.includes(file.id));

  const toggleSelectAllVisible = () => {
    if (areAllVisibleSelected) {
      const visibleSet = new Set(visibleFiles.map((file) => file.id));
      setSelectedFileIds((previous) => previous.filter((id) => !visibleSet.has(id)));
      return;
    }
    const next = new Set(selectedFileIds);
    visibleFiles.forEach((file) => next.add(file.id));
    setSelectedFileIds(Array.from(next));
  };

  const clearSelection = () => setSelectedFileIds([]);

  const pendingDeleteSeconds = useMemo(() => {
    if (!pendingDelete) return 0;
    return Math.max(0, Math.ceil((pendingDelete.expiresAt - Date.now()) / 1000));
  }, [pendingDelete, deleteCountdownTick]);

  const canMoveSelection = hasSelection && Boolean(onMoveFilesToGroup);
  const canUploadFilesToGroup = Boolean(onUploadFiles && onMoveFilesToGroup && fileGroups.length > 0 && uploadGroupId);
  const canIndexUrlsToGroup = Boolean(onUploadUrls && onMoveFilesToGroup && fileGroups.length > 0 && uploadGroupId);
  const canRenameGroup = Boolean(manageGroupId && manageGroupName.trim() && onRenameFileGroup);
  const canDeleteGroup = Boolean(manageGroupId && onDeleteFileGroup);

  const {
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
  } = useFilesViewActions({
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
    onOpenPdfPreview: () => setIsPdfPreviewModalOpen(true),
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
  });

  return (
    <div className="flex h-full min-h-0 flex-1 overflow-hidden bg-[#f5f5f7]">
      <UploadSidebar
        fileGroups={fileGroups}
        uploadGroupId={uploadGroupId}
        setUploadGroupId={setUploadGroupId}
        uploadTab={uploadTab}
        setUploadTab={setUploadTab}
        urlText={urlText}
        setUrlText={setUrlText}
        forceReindex={forceReindex}
        setForceReindex={setForceReindex}
        isSubmitting={isSubmitting}
        canUploadFilesToGroup={canUploadFilesToGroup}
        canIndexUrlsToGroup={canIndexUrlsToGroup}
        handleUrlIndex={handleUrlIndex}
        handleFileInputChange={handleFileInputChange}
        fileInputRef={fileInputRef}
        uploadStatus={uploadStatus}
        uploadProgressPercent={uploadProgressPercent}
        uploadProgressLabel={uploadProgressLabel}
        onCancelUpload={onCancelFileUpload}
        isCancelingUpload={isCancelingUpload}
        recentJobs={recentJobs}
      />

      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-8">
        <MainPanel
          filterText={filterText}
          setFilterText={setFilterText}
          sortField={sortField}
          setSortField={setSortField}
          sortDir={sortDir}
          setSortDir={setSortDir}
          kindFilter={kindFilter}
          setKindFilter={setKindFilter}
          groupSummaryCount={groupSummary.length}
          groupViewMode={groupViewMode}
          setGroupViewMode={setGroupViewMode}
          onCreateGroupModalOpen={() => {
            setQuickGroupName("");
            setShowCreateGroupModal(true);
          }}
          canCreateGroup={Boolean(onCreateFileGroup)}
          groupRows={groupRows}
          activeGroupFilter={activeGroupFilter}
          setActiveGroupFilter={setActiveGroupFilter}
          dragOverGroupId={dragOverGroupId}
          setDragOverGroupId={setDragOverGroupId}
          draggingFileId={draggingFileId}
          canMoveFiles={Boolean(onMoveFilesToGroup)}
          onDropFilesIntoGroup={dropFilesIntoGroup}
          activeGroupRecord={activeGroupRecord}
          manageGroupName={manageGroupName}
          setManageGroupName={setManageGroupName}
          handleRenameGroup={handleRenameGroup}
          handleDeleteGroup={handleDeleteGroup}
          isManagingGroup={isManagingGroup}
          canRenameGroup={canRenameGroup}
          canDeleteGroup={canDeleteGroup}
          pendingDelete={pendingDelete ? { count: pendingDelete.count } : null}
          pendingDeleteSeconds={pendingDeleteSeconds}
          handleUndoDelete={handleUndoDelete}
          handleDeleteNow={handleDeleteNow}
          actionMessage={actionMessage}
          viewMode={viewMode}
          setViewMode={setViewMode}
          visibleFiles={visibleFiles}
          selectedFileIds={selectedFileIds}
          toggleSelectAllVisible={toggleSelectAllVisible}
          areAllVisibleSelected={areAllVisibleSelected}
          toggleFileSelection={toggleFileSelection}
          startFileDrag={startFileDrag}
          endFileDrag={endFileDrag}
          groupsByFileId={groupsByFileId}
          citationFocus={citationFocus}
          citationRawUrl={citationRawUrl}
        />
      </div>

      <FilesViewOverlays
        showCreateGroupModal={showCreateGroupModal}
        setShowCreateGroupModal={setShowCreateGroupModal}
        quickGroupName={quickGroupName}
        setQuickGroupName={setQuickGroupName}
        handleCreateQuickGroup={handleCreateQuickGroup}
        isCreatingGroup={isCreatingGroup}
        canCreateGroup={Boolean(onCreateFileGroup)}
        hasSelection={hasSelection}
        selectedCount={selectedCount}
        focusPdfPreview={focusPdfPreview}
        selectedPdfPreviewUrl={selectedPdfPreviewUrl}
        targetGroupId={targetGroupId}
        setTargetGroupId={setTargetGroupId}
        hasGroups={hasGroups}
        fileGroups={fileGroups}
        handleMoveSelected={handleMoveSelected}
        isMovingSelection={isMovingSelection}
        canMoveSelection={canMoveSelection}
        clearSelection={clearSelection}
        handleDeleteSelected={handleDeleteSelected}
        isDeletingSelection={isDeletingSelection}
        canDeleteFiles={Boolean(onDeleteFiles)}
        pendingDeleteSeconds={pendingDeleteSeconds}
        pendingDeleteActive={pendingDelete !== null}
        deleteConfirmation={deleteConfirmation}
        deleteConfirmText={deleteConfirmText}
        setDeleteConfirmText={setDeleteConfirmText}
        handleCancelDeleteConfirmation={handleCancelDeleteConfirmation}
        handleConfirmDeleteAfterTyping={handleConfirmDeleteAfterTyping}
      />

      <PdfPreviewModal
        isOpen={isPdfPreviewModalOpen}
        selectedPdfPreviewUrl={selectedPdfPreviewUrl}
        selectedPdfFile={selectedPdfFile}
        onClose={() => setIsPdfPreviewModalOpen(false)}
      />
    </div>
  );
}
