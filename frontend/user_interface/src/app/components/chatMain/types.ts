import type { UploadResponse } from "../../../api/client";
import type { AgentActivityEvent, ChatAttachment, ChatTurn, CitationFocus } from "../../types";

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
      agentMode?: "ask" | "company_agent";
      accessMode?: "restricted" | "full_access";
    },
  ) => Promise<void>;
  onUploadFiles: (files: FileList) => Promise<UploadResponse>;
  isSending: boolean;
  citationMode: string;
  onCitationModeChange: (mode: string) => void;
  mindmapEnabled: boolean;
  onMindmapEnabledChange: (enabled: boolean) => void;
  onCitationClick: (citation: CitationFocus) => void;
  agentMode: "ask" | "company_agent";
  onAgentModeChange: (mode: "ask" | "company_agent") => void;
  accessMode: "restricted" | "full_access";
  onAccessModeChange: (mode: "restricted" | "full_access") => void;
  activityEvents: AgentActivityEvent[];
  isActivityStreaming: boolean;
};

type AttachmentStatus = "uploading" | "indexed" | "error";

type ComposerAttachment = {
  id: string;
  name: string;
  status: AttachmentStatus;
  message?: string;
  fileId?: string;
  localUrl?: string;
  mimeType?: string;
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
