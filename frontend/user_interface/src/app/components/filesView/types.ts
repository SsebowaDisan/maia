import type {
  BulkDeleteFilesResponse,
  DeleteFileGroupResponse,
  FileGroupRecord,
  FileGroupResponse,
  FileRecord,
  IngestionJob,
  MoveFilesToGroupResponse,
  UploadResponse,
} from "../../../api/client";
import type { CitationFocus } from "../../types";

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
type UploadTab = "upload" | "webLinks";
type GridMode = "table" | "cards";

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

type GroupRow = {
  id: string;
  name: string;
  count: number;
  droppable: boolean;
};

export type {
  DeleteConfirmationState,
  FileKind,
  FilesViewProps,
  GridMode,
  GroupRow,
  PendingDeleteJob,
  SelectOption,
  SortField,
  UploadTab,
};
