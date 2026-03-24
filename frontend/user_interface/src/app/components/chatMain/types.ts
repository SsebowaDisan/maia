import type { UploadResponse } from "../../../api/client";
import type { FileGroupRecord, FileRecord } from "../../../api/client";
import type { SidebarProject } from "../../appShell/types";
import type {
  AgentActivityEvent,
  ChatAttachment,
  ChatTurn,
  CitationFocus,
  ClarificationPrompt,
} from "../../types";

type ChatMainProps = {
  onToggleInfoPanel: () => void;
  isInfoPanelOpen: boolean;
  chatTurns: ChatTurn[];
  selectedTurnIndex: number | null;
  onSelectTurn: (turnIndex: number) => void;
  onUpdateUserTurn: (turnIndex: number, message: string) => void;
  onSendMessage: (
    message: string,
    attachments?: ChatAttachment[],
    options?: {
      citationMode?: string;
      useMindmap?: boolean;
      mindmapSettings?: Record<string, unknown>;
      mindmapFocus?: Record<string, unknown>;
      settingOverrides?: Record<string, unknown>;
      agentMode?: "ask" | "rag" | "company_agent" | "deep_search";
      agentId?: string;
      accessMode?: "restricted" | "full_access";
    },
  ) => Promise<void>;
  onUploadFiles: (
    files: FileList,
    options?: { onUploadProgress?: (loadedBytes: number, totalBytes: number) => void },
  ) => Promise<UploadResponse>;
  onCreateFileIngestionJob?: (
    files: FileList,
    options?: {
      reindex?: boolean;
      scope?: "persistent" | "chat_temp";
      onUploadProgress?: (loadedBytes: number, totalBytes: number) => void;
    },
  ) => Promise<{
    id: string;
    status: string;
    total_items: number;
    processed_items: number;
    bytes_total?: number;
    bytes_indexed?: number;
    items: { status: string; file_id?: string; message?: string }[];
    errors: string[];
    file_ids: string[];
    message: string;
  }>;
  availableDocuments?: FileRecord[];
  availableGroups?: FileGroupRecord[];
  availableProjects?: SidebarProject[];
  isSending: boolean;
  citationMode: string;
  onCitationModeChange: (mode: string) => void;
  mindmapEnabled: boolean;
  onMindmapEnabledChange: (enabled: boolean) => void;
  mindmapMaxDepth: number;
  onMindmapMaxDepthChange: (depth: number) => void;
  mindmapIncludeReasoning: boolean;
  onMindmapIncludeReasoningChange: (enabled: boolean) => void;
  mindmapMapType: "structure" | "evidence" | "work_graph" | "context_mindmap";
  onMindmapMapTypeChange: (mapType: "structure" | "evidence" | "work_graph" | "context_mindmap") => void;
  onCitationClick: (citation: CitationFocus) => void;
  citationFocus?: CitationFocus | null;
  agentMode: "ask" | "rag" | "company_agent" | "deep_search" | "brain";
  onAgentModeChange: (mode: "ask" | "rag" | "company_agent" | "deep_search" | "brain") => void;
  accessMode: "restricted" | "full_access";
  onAccessModeChange: (mode: "restricted" | "full_access") => void;
  activityEvents: AgentActivityEvent[];
  isActivityStreaming: boolean;
  clarificationPrompt: ClarificationPrompt | null;
  onDismissClarificationPrompt: () => void;
  onSubmitClarificationPrompt: (answers: string[]) => Promise<void>;
};

type AttachmentStatus = "uploading" | "indexing" | "indexed" | "error";

type ComposerAttachment = {
  id: string;
  name: string;
  status: AttachmentStatus;
  message?: string;
  fileId?: string;
  localUrl?: string;
  mimeType?: string;
  kind?: "file" | "project";
  entityId?: string;
};

type FilePreviewAttachment = {
  name: string;
  fileId?: string;
  localUrl?: string;
  mimeType?: string;
  status?: AttachmentStatus;
  message?: string;
};

export type {
  AttachmentStatus,
  ChatMainProps,
  ComposerAttachment,
  FilePreviewAttachment,
};
