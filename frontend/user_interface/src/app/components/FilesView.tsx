import { type ChangeEvent, type DragEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpDown,
  CheckSquare,
  ChevronDown,
  Eye,
  FolderPlus,
  HelpCircle,
  LayoutGrid,
  List,
  Search,
  Square,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { buildRawFileUrl } from "../../api/client";
import type {
  BulkDeleteFilesResponse,
  DeleteFileGroupResponse,
  FileGroupRecord,
  FileGroupResponse,
  FileRecord,
  IngestionJob,
  MoveFilesToGroupResponse,
  UploadResponse,
} from "../../api/client";
import type { CitationFocus } from "../types";

interface FilesViewProps {
  citationFocus?: CitationFocus | null;
  indexId?: number | null;
  files?: FileRecord[];
  fileGroups?: FileGroupRecord[];
  onRefreshFiles?: () => Promise<void>;
  onUploadFiles?: (
    files: FileList,
    options?: {
      scope?: "persistent" | "chat_temp";
      reindex?: boolean;
    },
  ) => Promise<UploadResponse>;
  onUploadUrls?: (
    urlText: string,
    options?: {
      reindex?: boolean;
      web_crawl_depth?: number;
      web_crawl_max_pages?: number;
      web_crawl_same_domain_only?: boolean;
      include_pdfs?: boolean;
      include_images?: boolean;
    },
  ) => Promise<UploadResponse>;
  onDeleteFiles?: (fileIds: string[]) => Promise<BulkDeleteFilesResponse>;
  onMoveFilesToGroup?: (
    fileIds: string[],
    options?: {
      groupId?: string;
      groupName?: string;
      mode?: "append" | "replace";
    },
  ) => Promise<MoveFilesToGroupResponse>;
  onCreateFileGroup?: (
    name: string,
    fileIds?: string[],
  ) => Promise<MoveFilesToGroupResponse>;
  onRenameFileGroup?: (groupId: string, name: string) => Promise<FileGroupResponse>;
  onDeleteFileGroup?: (groupId: string) => Promise<DeleteFileGroupResponse>;
  ingestionJobs?: IngestionJob[];
  onRefreshIngestionJobs?: () => Promise<void>;
  uploadStatus?: string;
}

type FileKind = "all" | "pdf" | "office" | "text" | "image" | "other";
type SortField = "date" | "name" | "size" | "token";
type PendingDeleteJob = {
  fileIds: string[];
  count: number;
  expiresAt: number;
  timeoutId: number;
};

type DeleteConfirmationState = {
  fileIds: string[];
  count: number;
  primaryName: string;
};

type SelectOption = {
  value: string;
  label: string;
};

const UNGROUPED_FILTER = "__ungrouped__";

function inferFileKind(name: string): FileKind {
  const ext = name.toLowerCase().split(".").pop() || "";
  if (ext === "pdf") return "pdf";
  if (["doc", "docx", "xls", "xlsx", "ppt", "pptx"].includes(ext)) return "office";
  if (["txt", "md", "csv", "json", "xml", "html", "mhtml"].includes(ext)) return "text";
  if (["png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "svg", "webp"].includes(ext))
    return "image";
  return "other";
}

function formatSize(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  const rounded = size >= 100 ? Math.round(size) : Math.round(size * 10) / 10;
  return `${rounded} ${units[idx]}`;
}

function formatDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function tokenNumber(note: Record<string, unknown>) {
  for (const key of ["token", "tokens", "n_tokens", "num_tokens", "token_count"]) {
    const raw = note[key];
    if (typeof raw === "number" && Number.isFinite(raw)) return raw;
    if (typeof raw === "string") {
      const parsed = Number(raw);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return 0;
}

function tokenText(note: Record<string, unknown>) {
  const value = tokenNumber(note);
  return value > 0 ? String(Math.round(value)) : "-";
}

function loaderText(note: Record<string, unknown>) {
  for (const key of ["loader", "reader", "doc_loader", "source_type", "type"]) {
    const raw = note[key];
    if (typeof raw === "string" && raw.trim()) return raw;
  }
  return "-";
}

function NeutralSelect({
  value,
  options,
  placeholder,
  disabled = false,
  buttonClassName,
  menuClassName,
  onChange,
}: {
  value: string;
  options: SelectOption[];
  placeholder: string;
  disabled?: boolean;
  buttonClassName: string;
  menuClassName?: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onPointerDown);
    return () => window.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (disabled) {
      setOpen(false);
    }
  }, [disabled]);

  const selectedOption = options.find((option) => option.value === value);
  const displayText = selectedOption?.label || placeholder;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => {
          if (!disabled) {
            setOpen((previous) => !previous);
          }
        }}
        disabled={disabled}
        className={`${buttonClassName} inline-flex items-center justify-between gap-2 disabled:opacity-45`}
      >
        <span className="truncate">{displayText}</span>
        <ChevronDown className={`h-3.5 w-3.5 text-[#6e6e73] transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open ? (
        <div
          className={`absolute z-20 mt-1 max-h-56 overflow-auto rounded-xl border border-black/[0.08] bg-white p-1 shadow-[0_12px_28px_rgba(0,0,0,0.12)] ${menuClassName || "left-0 right-0"}`}
        >
          {options.length ? (
            options.map((option) => {
              const isActive = option.value === value;
              return (
                <button
                  key={option.value || "__empty__"}
                  type="button"
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className={`w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] ${
                    isActive
                      ? "bg-[#1d1d1f] text-white"
                      : "text-[#1d1d1f] hover:bg-[#f5f5f7]"
                  }`}
                >
                  {option.label}
                </button>
              );
            })
          ) : (
            <p className="px-2.5 py-2 text-[12px] text-[#8d8d93]">No options</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export function FilesView({
  citationFocus = null,
  indexId = null,
  files = [],
  fileGroups = [],
  onRefreshFiles,
  onUploadFiles,
  onUploadUrls,
  onDeleteFiles,
  onMoveFilesToGroup,
  onCreateFileGroup,
  onRenameFileGroup,
  onDeleteFileGroup,
  ingestionJobs = [],
  onRefreshIngestionJobs,
  uploadStatus = "",
}: FilesViewProps) {
  const [uploadTab, setUploadTab] = useState<"upload" | "webLinks">("upload");
  const [filterText, setFilterText] = useState("");
  const [urlText, setUrlText] = useState("");
  const [forceReindex, setForceReindex] = useState(false);
  const [kindFilter, setKindFilter] = useState<FileKind>("all");
  const [sortField, setSortField] = useState<SortField>("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [viewMode, setViewMode] = useState<"table" | "cards">("table");
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
  const [deleteConfirmation, setDeleteConfirmation] = useState<DeleteConfirmationState | null>(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [pendingDelete, setPendingDelete] = useState<PendingDeleteJob | null>(null);
  const [deleteCountdownTick, setDeleteCountdownTick] = useState(0);
  const [isDeletingSelection, setIsDeletingSelection] = useState(false);
  const [isMovingSelection, setIsMovingSelection] = useState(false);
  const [isManagingGroup, setIsManagingGroup] = useState(false);
  const [isCreatingGroup, setIsCreatingGroup] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pdfPreviewRef = useRef<HTMLDivElement>(null);

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
    const activeGroup = activeGroupFilter === "all" || activeGroupFilter === UNGROUPED_FILTER
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
      return {
        ...group,
        count,
      };
    });
  }, [fileGroups, files]);

  const selectedFiles = useMemo(() => {
    if (!selectedFileIds.length) return [];
    const selectedSet = new Set(selectedFileIds);
    return files.filter((file) => selectedSet.has(file.id));
  }, [files, selectedFileIds]);

  const selectedCount = selectedFiles.length;
  const hasSelection = selectedFiles.length > 0;
  const hasGroups = groupSummary.length > 0;
  const activeGroupRecord = useMemo(
    () =>
      activeGroupFilter === "all" || activeGroupFilter === UNGROUPED_FILTER
        ? null
        : fileGroups.find((group) => group.id === activeGroupFilter) || null,
    [activeGroupFilter, fileGroups],
  );
  const ungroupedCount = useMemo(
    () => files.filter((file) => !groupedFileIds.has(file.id)).length,
    [files, groupedFileIds],
  );

  const selectedPdfFile = useMemo(
    () => selectedFiles.find((file) => inferFileKind(file.name) === "pdf") || null,
    [selectedFiles],
  );

  const selectedPdfPreviewUrl = useMemo(() => {
    if (!selectedPdfFile) return null;
    const raw = buildRawFileUrl(selectedPdfFile.id, {
      indexId: typeof indexId === "number" ? indexId : undefined,
    });
    return `${raw}#view=FitH`;
  }, [selectedPdfFile, indexId]);

  const citationRawUrl = useMemo(() => {
    if (!citationFocus?.fileId) return null;
    return buildRawFileUrl(citationFocus.fileId, {
      indexId: typeof indexId === "number" ? indexId : undefined,
    });
  }, [citationFocus, indexId]);

  const recentJobs = useMemo(
    () => [...ingestionJobs].sort((a, b) => (a.date_created || "").localeCompare(b.date_created || "")).reverse().slice(0, 6),
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

  const focusPdfPreview = () => {
    if (!selectedPdfPreviewUrl) {
      setActionMessage("Select at least one PDF to preview.");
      window.setTimeout(() => setActionMessage(""), 2200);
      return;
    }
    pdfPreviewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const clearPendingDelete = () => {
    if (!pendingDelete) return;
    window.clearTimeout(pendingDelete.timeoutId);
    setPendingDelete(null);
  };

  const queueDeletion = (fileIds: string[]) => {
    if (!fileIds.length) return;
    if (pendingDelete) {
      window.clearTimeout(pendingDelete.timeoutId);
    }
    const expiresAt = Date.now() + 5000;
    const timeoutId = window.setTimeout(() => {
      void commitPendingDelete(fileIds);
    }, 5000);
    setPendingDelete({
      fileIds,
      count: fileIds.length,
      expiresAt,
      timeoutId,
    });
    setActionMessage(`Queued ${fileIds.length} file(s) for deletion. Undo within 5s.`);
  };

  const commitPendingDelete = async (fileIds: string[]) => {
    if (!fileIds.length || !onDeleteFiles) return;
    setIsDeletingSelection(true);
    try {
      const response = await onDeleteFiles(fileIds);
      const deletedCount = response.deleted_ids.length;
      const failedCount = response.failed.length;
      const failedSnippet =
        failedCount > 0
          ? ` ${response.failed
              .slice(0, 2)
              .map((item) => item.message || item.status || item.file_id)
              .join(" | ")}`
          : "";
      setActionMessage(
        failedCount > 0
          ? `Deleted ${deletedCount} file(s), ${failedCount} failed.${failedSnippet}`
          : `Deleted ${deletedCount} file(s).`,
      );
      setSelectedFileIds((previous) =>
        previous.filter((fileId) => !response.deleted_ids.includes(fileId)),
      );
    } catch (error) {
      setActionMessage(`Delete failed: ${String(error)}`);
    } finally {
      setIsDeletingSelection(false);
      setPendingDelete(null);
      window.setTimeout(() => setActionMessage(""), 2600);
    }
  };

  const handleDeleteSelected = () => {
    if (!selectedFiles.length || !onDeleteFiles || isDeletingSelection) return;
    const fileIds = Array.from(new Set(selectedFiles.map((file) => file.id)));
    if (!fileIds.length) return;
    setDeleteConfirmation({
      fileIds,
      count: fileIds.length,
      primaryName: selectedFiles[0]?.name || "selected file",
    });
    setDeleteConfirmText("");
  };

  const handleCancelDeleteConfirmation = () => {
    setDeleteConfirmation(null);
    setDeleteConfirmText("");
  };

  const handleConfirmDeleteAfterTyping = () => {
    if (!deleteConfirmation) return;
    if (deleteConfirmText.trim().toLowerCase() !== "delete") return;
    queueDeletion(deleteConfirmation.fileIds);
    setDeleteConfirmation(null);
    setDeleteConfirmText("");
  };

  const handleUndoDelete = () => {
    clearPendingDelete();
    setActionMessage("Deletion canceled.");
    window.setTimeout(() => setActionMessage(""), 2200);
  };

  const handleDeleteNow = () => {
    if (!pendingDelete) return;
    const fileIds = [...pendingDelete.fileIds];
    window.clearTimeout(pendingDelete.timeoutId);
    setPendingDelete(null);
    void commitPendingDelete(fileIds);
  };

  const startFileDrag = (event: DragEvent<HTMLElement>, fileId: string) => {
    if (!onMoveFilesToGroup) return;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", fileId);
    setDraggingFileId(fileId);
  };

  const endFileDrag = () => {
    setDraggingFileId(null);
    setDragOverGroupId(null);
  };

  const moveIntoGroup = async (fileIds: string[], groupId: string, source: "manual" | "drag") => {
    if (!fileIds.length || !onMoveFilesToGroup || !groupId) return;
    setIsMovingSelection(true);
    try {
      const response = await onMoveFilesToGroup(fileIds, {
        groupId,
        mode: "append",
      });
      setTargetGroupId(response.group.id);
      setActiveGroupFilter(response.group.id);
      const movedCount = response.moved_ids.length;
      const skippedCount = response.skipped_ids.length;
      const prefix = source === "drag" ? "Dropped" : "Moved";
      setActionMessage(
        skippedCount > 0
          ? `${prefix} ${movedCount} file(s) into "${response.group.name}", ${skippedCount} skipped.`
          : `${prefix} ${movedCount} file(s) into "${response.group.name}".`,
      );
    } catch (error) {
      setActionMessage(`Move failed: ${String(error)}`);
    } finally {
      setIsMovingSelection(false);
      window.setTimeout(() => setActionMessage(""), 2600);
    }
  };

  const dropFilesIntoGroup = async (groupId: string, sourceFileId: string | null) => {
    if (!onMoveFilesToGroup) return;
    const fromSelection =
      sourceFileId && selectedFileIds.includes(sourceFileId) && selectedFileIds.length > 0;
    const fileIds = fromSelection
      ? [...selectedFileIds]
      : sourceFileId
        ? [sourceFileId]
        : [];
    if (!fileIds.length) {
      setActionMessage("Select or drag a file first.");
      window.setTimeout(() => setActionMessage(""), 2200);
      return;
    }
    await moveIntoGroup(fileIds, groupId, "drag");
  };

  const handleMoveSelected = async () => {
    if (!selectedFiles.length || !onMoveFilesToGroup) return;
    if (!targetGroupId) {
      setActionMessage("Choose a destination group.");
      window.setTimeout(() => setActionMessage(""), 2400);
      return;
    }
    await moveIntoGroup(
      selectedFiles.map((file) => file.id),
      targetGroupId,
      "manual",
    );
  };

  const handleCreateQuickGroup = async () => {
    if (!onCreateFileGroup) return;
    const cleanName = quickGroupName.trim();
    if (!cleanName) {
      setActionMessage("Enter a group name.");
      window.setTimeout(() => setActionMessage(""), 2200);
      return;
    }

    setIsCreatingGroup(true);
    try {
      const selectedIds = selectedFiles.map((file) => file.id);
      const response = await onCreateFileGroup(cleanName, selectedIds);
      setQuickGroupName("");
      setActiveGroupFilter(response.group.id);
      setManageGroupId(response.group.id);
      setManageGroupName(response.group.name);
      setTargetGroupId(response.group.id);
      setShowCreateGroupModal(false);
      if (selectedIds.length > 0) {
        setActionMessage(
          `Created "${response.group.name}" and added ${response.moved_ids.length} selected file(s).`,
        );
      } else {
        setActionMessage(`Created "${response.group.name}".`);
      }
    } catch (error) {
      setActionMessage(`Create group failed: ${String(error)}`);
    } finally {
      setIsCreatingGroup(false);
      window.setTimeout(() => setActionMessage(""), 2600);
    }
  };

  const handleRenameGroup = async () => {
    if (!manageGroupId || !onRenameFileGroup) return;
    const cleanName = manageGroupName.trim();
    if (!cleanName) {
      setActionMessage("Group name is required.");
      window.setTimeout(() => setActionMessage(""), 2400);
      return;
    }
    setIsManagingGroup(true);
    try {
      const response = await onRenameFileGroup(manageGroupId, cleanName);
      setManageGroupName(response.group.name);
      setActionMessage(`Renamed group to "${response.group.name}".`);
    } catch (error) {
      setActionMessage(`Rename failed: ${String(error)}`);
    } finally {
      setIsManagingGroup(false);
      window.setTimeout(() => setActionMessage(""), 2600);
    }
  };

  const handleDeleteGroup = async () => {
    if (!manageGroupId || !onDeleteFileGroup) return;
    const group = fileGroups.find((item) => item.id === manageGroupId);
    const groupName = group?.name || "this group";
    const shouldDelete = window.confirm(`Delete group "${groupName}"?`);
    if (!shouldDelete) return;

    setIsManagingGroup(true);
    try {
      await onDeleteFileGroup(manageGroupId);
      setManageGroupId("");
      setManageGroupName("");
      setActionMessage(`Deleted group "${groupName}".`);
    } catch (error) {
      setActionMessage(`Delete group failed: ${String(error)}`);
    } finally {
      setIsManagingGroup(false);
      window.setTimeout(() => setActionMessage(""), 2600);
    }
  };

  const pendingDeleteSeconds = useMemo(() => {
    if (!pendingDelete) return 0;
    return Math.max(0, Math.ceil((pendingDelete.expiresAt - Date.now()) / 1000));
  }, [pendingDelete, deleteCountdownTick]);

  const canMoveSelection = hasSelection && Boolean(onMoveFilesToGroup);
  const canUploadFilesToGroup = Boolean(
    onUploadFiles && onMoveFilesToGroup && fileGroups.length > 0 && uploadGroupId,
  );
  const canIndexUrlsToGroup = Boolean(
    onUploadUrls && onMoveFilesToGroup && fileGroups.length > 0 && uploadGroupId,
  );

  const extractSuccessfulFileIds = (response: UploadResponse) => {
    const byItem = response.items
      .filter((item) => item.status === "success" && item.file_id)
      .map((item) => item.file_id as string);
    return Array.from(new Set([...response.file_ids, ...byItem]));
  };

  const handleFileInputChange = async (event: ChangeEvent<HTMLInputElement>) => {
    if (!event.target.files || !event.target.files.length) return;
    if (!onUploadFiles || !onMoveFilesToGroup) {
      setActionMessage("Upload action is not available.");
      window.setTimeout(() => setActionMessage(""), 2400);
      event.target.value = "";
      return;
    }
    if (!fileGroups.length) {
      setActionMessage("Create a group first before uploading files.");
      window.setTimeout(() => setActionMessage(""), 2600);
      event.target.value = "";
      return;
    }
    if (!uploadGroupId) {
      setActionMessage("Choose a destination group before uploading.");
      window.setTimeout(() => setActionMessage(""), 2600);
      event.target.value = "";
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await onUploadFiles(event.target.files, {
        reindex: forceReindex,
        scope: "persistent",
      });
      const successFileIds = extractSuccessfulFileIds(response);
      if (!successFileIds.length) {
        setActionMessage(response.errors[0] || "No files were indexed.");
        window.setTimeout(() => setActionMessage(""), 2600);
        return;
      }
      const moveResponse = await onMoveFilesToGroup(successFileIds, {
        groupId: uploadGroupId,
        mode: "append",
      });
      const failedCount = response.items.filter((item) => item.status !== "success").length;
      setActionMessage(
        failedCount > 0
          ? `Uploaded ${successFileIds.length} file(s) to "${moveResponse.group.name}", ${failedCount} failed.`
          : `Uploaded ${successFileIds.length} file(s) to "${moveResponse.group.name}".`,
      );
      await onRefreshIngestionJobs?.();
      await onRefreshFiles?.();
      window.setTimeout(() => setActionMessage(""), 2600);
    } catch (error) {
      setActionMessage(`Upload failed: ${String(error)}`);
      window.setTimeout(() => setActionMessage(""), 2600);
    } finally {
      setIsSubmitting(false);
      event.target.value = "";
    }
  };

  const handleUrlIndex = async () => {
    if (!urlText.trim()) return;
    if (!onUploadUrls || !onMoveFilesToGroup) {
      setActionMessage("URL indexing is not available.");
      window.setTimeout(() => setActionMessage(""), 2400);
      return;
    }
    if (!fileGroups.length) {
      setActionMessage("Create a group first before indexing URLs.");
      window.setTimeout(() => setActionMessage(""), 2600);
      return;
    }
    if (!uploadGroupId) {
      setActionMessage("Choose a destination group before indexing URLs.");
      window.setTimeout(() => setActionMessage(""), 2600);
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await onUploadUrls(urlText, {
        reindex: forceReindex,
        web_crawl_depth: 0,
        web_crawl_max_pages: 0,
        web_crawl_same_domain_only: true,
        include_pdfs: true,
        include_images: true,
      });
      const successFileIds = extractSuccessfulFileIds(response);
      if (!successFileIds.length) {
        setActionMessage(response.errors[0] || "No URL content was indexed.");
        window.setTimeout(() => setActionMessage(""), 2600);
        return;
      }
      const moveResponse = await onMoveFilesToGroup(successFileIds, {
        groupId: uploadGroupId,
        mode: "append",
      });
      const failedCount = response.items.filter((item) => item.status !== "success").length;
      setActionMessage(
        failedCount > 0
          ? `Indexed ${successFileIds.length} source(s) to "${moveResponse.group.name}", ${failedCount} failed.`
          : `Indexed ${successFileIds.length} source(s) to "${moveResponse.group.name}".`,
      );
      await onRefreshIngestionJobs?.();
      await onRefreshFiles?.();
      setUrlText("");
      window.setTimeout(() => setActionMessage(""), 2600);
    } catch (error) {
      setActionMessage(`URL indexing failed: ${String(error)}`);
      window.setTimeout(() => setActionMessage(""), 2600);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden bg-[#f5f5f7]">
      <div className="w-[320px] min-h-0 overflow-y-auto border-r border-black/[0.06] bg-white px-6 py-8">
        <p className="text-[18px] font-semibold tracking-tight text-[#1d1d1f]">Upload Files</p>
        <p className="mt-1 text-[13px] text-[#6e6e73]">Upload into a selected group.</p>

        <p className="mt-6 text-[11px] uppercase tracking-[0.08em] text-[#8d8d93]">Destination Group</p>
        <NeutralSelect
          value={uploadGroupId}
          placeholder={fileGroups.length ? "Choose group" : "Create a group first"}
          disabled={fileGroups.length === 0}
          options={fileGroups.map((group) => ({ value: group.id, label: group.name }))}
          onChange={setUploadGroupId}
          buttonClassName="mt-2 h-11 w-full rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] text-[#1d1d1f]"
        />

        <div className="mt-6 rounded-3xl border border-black/[0.06] bg-[#fafafc] p-5">
          <div className="inline-flex rounded-full border border-black/[0.06] bg-white p-1">
            <button
              onClick={() => setUploadTab("upload")}
              className={`rounded-full px-4 py-1.5 text-[12px] ${
                uploadTab === "upload" ? "bg-[#1d1d1f] text-white" : "text-[#6e6e73]"
              }`}
            >
              Files
            </button>
            <button
              onClick={() => setUploadTab("webLinks")}
              className={`rounded-full px-4 py-1.5 text-[12px] ${
                uploadTab === "webLinks" ? "bg-[#1d1d1f] text-white" : "text-[#6e6e73]"
              }`}
            >
              Links
            </button>
          </div>

          {uploadTab === "upload" ? (
            <>
              <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFileInputChange} />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isSubmitting || !canUploadFilesToGroup}
                className="mt-5 w-full rounded-2xl border border-black/[0.08] bg-white px-6 py-14 text-center transition-colors hover:bg-[#fcfcfd] disabled:opacity-50"
              >
                <Upload className="mx-auto mb-3 h-8 w-8 text-[#8d8d93]" />
                <p className="text-[15px] text-[#1d1d1f]">Drag files here</p>
                <p className="mt-1 text-[14px] text-[#6e6e73]">or click to browse</p>
              </button>
            </>
          ) : (
            <textarea
              value={urlText}
              onChange={(event) => setUrlText(event.target.value)}
              placeholder="https://example.com"
              className="mt-5 min-h-[140px] w-full rounded-2xl border border-black/[0.08] bg-white px-3 py-3 text-[13px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
            />
          )}

          <div className="mt-5 flex items-center justify-between">
            <span className="text-[13px] text-[#1d1d1f]">Force reindex</span>
            <button
              type="button"
              role="switch"
              aria-checked={forceReindex}
              onClick={() => setForceReindex((value) => !value)}
              className={`relative h-6 w-11 rounded-full transition-colors ${
                forceReindex ? "bg-[#1d1d1f]" : "bg-[#d7d7dc]"
              }`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                  forceReindex ? "translate-x-[22px]" : "translate-x-[2px]"
                }`}
              />
            </button>
          </div>

          <button
            type="button"
            onClick={() => (uploadTab === "upload" ? fileInputRef.current?.click() : void handleUrlIndex())}
            disabled={isSubmitting || (uploadTab === "upload" ? !canUploadFilesToGroup : !canIndexUrlsToGroup)}
            className="mt-5 h-11 w-full rounded-xl bg-[#1d1d1f] text-[14px] text-white hover:bg-[#2c2c30] disabled:opacity-40"
          >
            {uploadTab === "upload" ? "Upload to Group" : "Index URLs to Group"}
          </button>
        </div>

        {uploadStatus ? <p className="mt-3 text-[12px] text-[#6e6e73]">{uploadStatus}</p> : null}

        <div className="mt-8">
          <div className="flex items-center justify-between">
            <p className="text-[12px] uppercase tracking-[0.08em] text-[#8d8d93]">Ingestion Jobs</p>
            <button onClick={() => void onRefreshIngestionJobs?.()} className="text-[12px] text-[#6e6e73] hover:text-[#1d1d1f]">
              Refresh
            </button>
          </div>
          <div className="mt-3 space-y-2">
            {recentJobs.length === 0 ? (
              <p className="text-[12px] text-[#8d8d93]">No jobs yet.</p>
            ) : (
              recentJobs.map((job) => (
                <div key={job.id} className="rounded-xl border border-black/[0.06] bg-white px-3 py-2.5">
                  <p className="truncate text-[12px] text-[#1d1d1f]">
                    {job.kind === "urls" ? "URL indexing" : "File indexing"}
                  </p>
                  <p className="text-[11px] text-[#8d8d93]">
                    {job.processed_items}/{job.total_items} | {job.status}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-8 py-8">
        <div className={`grid gap-6 ${selectedPdfPreviewUrl ? "xl:grid-cols-[minmax(0,1fr)_440px]" : "grid-cols-1"}`}>
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
                  onClick={() => setSortDir((value) => (value === "asc" ? "desc" : "asc"))}
                  className="inline-flex h-11 items-center gap-1.5 rounded-xl border border-black/[0.08] px-3 text-[13px] text-[#1d1d1f]"
                >
                  <ArrowUpDown className="h-4 w-4" />
                  {sortDir === "asc" ? "Asc" : "Desc"}
                </button>
                <div className="ml-auto inline-flex items-center gap-4">
                  <button
                    onClick={() => setViewMode("table")}
                    className={`inline-flex items-center gap-1 text-[12px] ${
                      viewMode === "table" ? "font-semibold text-[#1d1d1f]" : "text-[#8d8d93]"
                    }`}
                  >
                    <List className="h-3.5 w-3.5" />
                    Table
                  </button>
                  <button
                    onClick={() => setViewMode("cards")}
                    className={`inline-flex items-center gap-1 text-[12px] ${
                      viewMode === "cards" ? "font-semibold text-[#1d1d1f]" : "text-[#8d8d93]"
                    }`}
                  >
                    <LayoutGrid className="h-3.5 w-3.5" />
                    Cards
                  </button>
                </div>
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

              <div className="mt-8">
                <div className="flex items-center justify-between">
                  <p className="text-[20px] font-semibold tracking-tight text-[#1d1d1f]">Groups</p>
                  <div className="flex items-center gap-3">
                    <span className="text-[12px] text-[#8d8d93]">{groupSummary.length} total</span>
                    <button
                      onClick={() => {
                        setQuickGroupName("");
                        setShowCreateGroupModal(true);
                      }}
                      disabled={!onCreateFileGroup}
                      className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] text-[#1d1d1f] hover:bg-[#f8f8fa] disabled:opacity-45"
                    >
                      <FolderPlus className="h-3.5 w-3.5" />
                      New Group
                    </button>
                  </div>
                </div>

                <div className="mt-4 overflow-hidden rounded-2xl border border-black/[0.06]">
                  <button
                    onClick={() => setActiveGroupFilter("all")}
                    className={`flex w-full items-center justify-between border-b border-[#f2f2f5] px-4 py-[22px] text-left ${
                      activeGroupFilter === "all" ? "bg-[#f7f7f9]" : "hover:bg-[#fafafd]"
                    }`}
                  >
                    <span className="text-[15px] font-medium text-[#1d1d1f]">All Files</span>
                    <span className="text-[13px] text-[#1d1d1f]/55">{files.length}</span>
                  </button>
                  <button
                    onClick={() => setActiveGroupFilter(UNGROUPED_FILTER)}
                    className={`flex w-full items-center justify-between border-b border-[#f2f2f5] px-4 py-[22px] text-left ${
                      activeGroupFilter === UNGROUPED_FILTER ? "bg-[#f7f7f9]" : "hover:bg-[#fafafd]"
                    }`}
                  >
                    <span className="text-[15px] font-medium text-[#1d1d1f]">Ungrouped</span>
                    <span className="text-[13px] text-[#1d1d1f]/55">{ungroupedCount}</span>
                  </button>
                  {groupSummary.map((group, index) => {
                    const isActive = activeGroupFilter === group.id;
                    return (
                      <button
                        key={group.id}
                        onClick={() => setActiveGroupFilter(group.id)}
                        onDragOver={(event) => {
                          if (!onMoveFilesToGroup) return;
                          event.preventDefault();
                          event.dataTransfer.dropEffect = "move";
                          setDragOverGroupId(group.id);
                        }}
                        onDragLeave={() => {
                          if (dragOverGroupId === group.id) {
                            setDragOverGroupId(null);
                          }
                        }}
                        onDrop={(event) => {
                          if (!onMoveFilesToGroup) return;
                          event.preventDefault();
                          const droppedId = event.dataTransfer.getData("text/plain") || draggingFileId || "";
                          setDragOverGroupId(null);
                          void dropFilesIntoGroup(group.id, droppedId || null);
                        }}
                        className={`flex w-full items-center justify-between px-4 py-[22px] text-left ${
                          index < groupSummary.length - 1 ? "border-b border-[#f2f2f5]" : ""
                        } ${
                          isActive || dragOverGroupId === group.id ? "bg-[#f7f7f9]" : "hover:bg-[#fafafd]"
                        }`}
                      >
                        <span className="truncate pr-3 text-[15px] font-medium text-[#1d1d1f]">{group.name}</span>
                        <span className="text-[13px] text-[#1d1d1f]/55">{group.count}</span>
                      </button>
                    );
                  })}
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
                      disabled={!manageGroupId || !manageGroupName.trim() || isManagingGroup || !onRenameFileGroup}
                      className="h-11 rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] text-[#1d1d1f] hover:bg-[#f8f8fa] disabled:opacity-45"
                    >
                      Rename
                    </button>
                    <button
                      onClick={() => void handleDeleteGroup()}
                      disabled={!manageGroupId || isManagingGroup || !onDeleteFileGroup}
                      className="h-11 rounded-xl border border-[#ffd3d6] bg-white px-3 text-[13px] text-[#b42318] disabled:opacity-45"
                    >
                      Delete
                    </button>
                  </div>
                ) : null}
              </div>

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

              {actionMessage ? (
                <p className="mt-6 text-[12px] text-[#6e6e73]">{actionMessage}</p>
              ) : null}

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
                            {areAllVisibleSelected ? (
                              <CheckSquare className="h-4 w-4" />
                            ) : (
                              <Square className="h-4 w-4" />
                            )}
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
                              draggable={Boolean(onMoveFilesToGroup)}
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
                                  {isSelected ? (
                                    <CheckSquare className="h-4 w-4" />
                                  ) : (
                                    <Square className="h-4 w-4" />
                                  )}
                                </button>
                              </td>
                              <td className="max-w-[340px] truncate px-4 py-5 text-[14px] text-[#1d1d1f]">{file.name}</td>
                              <td className="px-4 py-5 text-[14px] text-[#1d1d1f]">{formatSize(file.size)}</td>
                              <td className="px-4 py-5 text-[14px] text-[#1d1d1f]">{tokenText(file.note || {})}</td>
                              <td className="px-4 py-5 text-[14px] text-[#1d1d1f]">{loaderText(file.note || {})}</td>
                              <td className="max-w-[260px] truncate px-4 py-5 text-[13px] text-[#6e6e73]">
                                {groupsByFileId.get(file.id)?.length
                                  ? groupsByFileId.get(file.id)!.join(", ")
                                  : "-"}
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
                          draggable={Boolean(onMoveFilesToGroup)}
                          onDragStart={(event) => startFileDrag(event, file.id)}
                          onDragEnd={endFileDrag}
                          onClick={() => toggleFileSelection(file.id)}
                          className={`rounded-xl border px-4 py-4 text-left ${
                            isSelected ? "border-[#1d1d1f] bg-[#f7f7f9]" : "border-black/[0.08] bg-white"
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            {isSelected ? (
                              <CheckSquare className="h-4 w-4 text-[#1d1d1f]" />
                            ) : (
                              <Square className="h-4 w-4 text-[#8d8d93]" />
                            )}
                            <p className="truncate text-[14px] font-medium text-[#1d1d1f]">{file.name}</p>
                          </div>
                          <p className="mt-1 text-[12px] text-[#6e6e73]">
                            {formatSize(file.size)} | {loaderText(file.note || {})}
                          </p>
                          <p className="mt-1 truncate text-[11px] text-[#8d8d93]">
                            {groupsByFileId.get(file.id)?.length
                              ? groupsByFileId.get(file.id)!.join(", ")
                              : "No group"}
                          </p>
                        </button>
                      );
                    })
                  )}
                </div>
              )}
            </div>

            {citationFocus && citationRawUrl ? (
              <div className="mt-6 rounded-2xl border border-black/[0.08] bg-white p-4">
                <p className="text-[12px] text-[#6e6e73] mb-2">Citation source</p>
                <a
                  href={citationRawUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[13px] text-[#2f2f34] hover:underline"
                >
                  Open {citationFocus.sourceName}
                </a>
              </div>
            ) : null}
          </div>

          {selectedPdfPreviewUrl ? (
            <div
              ref={pdfPreviewRef}
              className="flex min-h-[420px] flex-col overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-sm xl:h-[calc(100vh-7.5rem)] xl:min-h-0"
            >
              <div className="px-4 py-3 border-b border-black/[0.06] bg-[#fafafa]">
                <p className="text-[12px] text-[#6e6e73]">PDF Preview</p>
                <p className="text-[13px] font-medium text-[#1d1d1f] truncate">{selectedPdfFile?.name}</p>
              </div>
              <iframe
                title="Selected PDF preview"
                src={selectedPdfPreviewUrl}
                className="flex-1 w-full bg-white"
              />
            </div>
          ) : selectedFiles.length > 0 ? (
            <div
              ref={pdfPreviewRef}
              className="rounded-2xl border border-black/[0.08] bg-white p-5 text-[13px] text-[#6e6e73]"
            >
              PDF preview is available when the current selection includes at least one PDF.
            </div>
          ) : null}
        </div>
      </div>

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
                disabled={isCreatingGroup || !onCreateFileGroup || !quickGroupName.trim()}
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
            <span className="px-2 text-[13px] font-medium text-[#1d1d1f]">
              {selectedCount} selected
            </span>
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
              disabled={isDeletingSelection || !onDeleteFiles || pendingDelete !== null}
              className="inline-flex h-9 items-center gap-1 rounded-lg border border-[#ffd3d6] bg-white px-2.5 text-[12px] text-[#b42318] disabled:opacity-45"
            >
              <Trash2 className="h-3.5 w-3.5" />
              {isDeletingSelection ? "Deleting..." : pendingDelete ? `Queued (${pendingDeleteSeconds}s)` : "Delete"}
            </button>
          </div>
        </div>
      ) : null}

      {deleteConfirmation ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/35 px-4">
          <div className="w-full max-w-[520px] rounded-2xl border border-black/[0.08] bg-white p-5 shadow-[0_18px_52px_rgba(0,0,0,0.2)]">
            <p className="text-[18px] font-semibold tracking-tight text-[#1d1d1f]">
              Confirm file deletion
            </p>
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
                className="h-9 px-3 rounded-lg border border-black/[0.08] text-[12px] text-[#1d1d1f] bg-white hover:bg-[#f8f8fa]"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDeleteAfterTyping}
                disabled={deleteConfirmText.trim().toLowerCase() !== "delete"}
                className="h-9 px-3 rounded-lg border border-[#ffd3d6] bg-[#fff5f5] text-[12px] text-[#b42318] disabled:opacity-45"
              >
                Delete Files
              </button>
            </div>
          </div>
        </div>
      ) : null}
      <button className="fixed bottom-6 right-6 w-9 h-9 rounded-full border border-black/[0.08] bg-white shadow-sm flex items-center justify-center text-[#86868b] hover:text-[#1d1d1f]">
        <HelpCircle className="w-5 h-5" />
      </button>
    </div>
  );
}
