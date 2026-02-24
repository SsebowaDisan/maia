import { type ChangeEvent, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import type { ConversationSummary, UploadResponse } from "../../api/client";

interface ChatSidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  conversations: ConversationSummary[];
  selectedConversationId: string | null;
  onSelectConversation: (conversationId: string) => void;
  onNewConversation: () => void;
  onUploadFiles: (files: FileList) => Promise<UploadResponse>;
  onUploadUrls: (urlText: string) => Promise<void>;
  uploadStatus: string;
  width?: number;
}

export function ChatSidebar({
  isCollapsed,
  onToggleCollapse,
  conversations,
  selectedConversationId,
  onSelectConversation,
  onNewConversation,
  onUploadFiles,
  onUploadUrls,
  uploadStatus,
  width = 300,
}: ChatSidebarProps) {
  const [urlText, setUrlText] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileInputChange = async (event: ChangeEvent<HTMLInputElement>) => {
    if (!event.target.files || !event.target.files.length) {
      return;
    }
    setIsUploading(true);
    try {
      await onUploadFiles(event.target.files);
    } catch {
      // Status messaging is handled by parent.
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  };

  const handleUrlSubmit = async () => {
    if (!urlText.trim()) {
      return;
    }
    setIsUploading(true);
    try {
      await onUploadUrls(urlText);
      setUrlText("");
    } catch {
      // Status messaging is handled by parent.
    } finally {
      setIsUploading(false);
    }
  };

  if (isCollapsed) {
    return (
      <div className="w-16 min-h-0 bg-white/80 backdrop-blur-xl border-r border-black/[0.06] flex flex-col items-center py-4">
        <button
          onClick={onToggleCollapse}
          className="p-2 rounded-lg hover:bg-black/5 transition-colors"
        >
          <ChevronRight className="w-5 h-5 text-[#86868b]" />
        </button>
      </div>
    );
  }

  return (
    <div
      className="min-h-0 bg-white/80 backdrop-blur-xl border-r border-black/[0.06] flex flex-col overflow-hidden"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="px-5 py-4 border-b border-black/[0.06]">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[18px] font-semibold tracking-tight text-[#1d1d1f]">
            Conversation
          </h2>
          <button
            onClick={onToggleCollapse}
            className="p-1.5 rounded-md hover:bg-black/5 transition-colors"
          >
            <ChevronRight className="w-4 h-4 text-[#86868b]" />
          </button>
        </div>

        <div className="relative mb-3">
          <select
            className="w-full px-3 py-2 bg-[#f5f5f7] border-0 rounded-lg text-[13px] text-[#1d1d1f] appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-black/10"
            value={selectedConversationId || ""}
            onChange={(event) => {
              if (event.target.value) {
                onSelectConversation(event.target.value);
              }
            }}
          >
            <option value="">Browse conversation</option>
            {conversations.map((conversation) => (
              <option key={conversation.id} value={conversation.id}>
                {conversation.name}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#86868b] pointer-events-none" />
        </div>

        <div className="flex items-center gap-2">
          <button className="flex items-center gap-1.5 px-3 py-1.5 bg-[#f5f5f7] rounded-lg hover:bg-[#e8e8ed] transition-all text-[13px] text-[#1d1d1f]">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Suggest chat</span>
          </button>
          <button className="p-1.5 rounded-lg hover:bg-black/5 transition-colors">
            <Pencil className="w-4 h-4 text-[#86868b]" />
          </button>
          <button className="p-1.5 rounded-lg hover:bg-black/5 transition-colors">
            <Trash2 className="w-4 h-4 text-[#86868b]" />
          </button>
          <button
            className="p-1.5 rounded-lg hover:bg-black/5 transition-colors"
            onClick={onNewConversation}
            title="New conversation"
          >
            <Plus className="w-4 h-4 text-[#86868b]" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="px-5 py-4 border-b border-black/[0.06]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[13px] font-medium text-[#1d1d1f]">
              File Collection
            </span>
          </div>
          <div className="h-px bg-black/[0.08]" />
        </div>

        <div className="px-5 py-4 border-b border-black/[0.06]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[13px] font-medium text-[#1d1d1f]">
              Quick Upload
            </span>
            <ChevronDown className="w-4 h-4 text-[#86868b]" />
          </div>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleFileInputChange}
          />

          <button
            className="w-full flex flex-col items-center justify-center py-8 px-4 bg-[#f5f5f7] rounded-xl border-2 border-dashed border-[#d2d2d7] hover:border-[#1d1d1f] hover:bg-[#ececef] transition-all"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
          >
            <Upload className="w-8 h-8 text-[#86868b] mb-2" />
            <p className="text-[13px] text-[#1d1d1f] mb-1">Drop File Here</p>
            <p className="text-[11px] text-[#86868b] mb-2">- or -</p>
            <p className="text-[13px] text-[#1d1d1f]">Click to Upload</p>
          </button>

          <textarea
            value={urlText}
            onChange={(event) => setUrlText(event.target.value)}
            placeholder="Or paste URLs (one per line)"
            className="w-full mt-3 px-3 py-2 bg-[#f5f5f7] border-0 rounded-lg text-[13px] text-[#1d1d1f] placeholder:text-[#86868b] focus:outline-none focus:ring-2 focus:ring-black/10 resize-none min-h-[80px]"
          />

          <button
            className="w-full mt-2 px-4 py-2 bg-[#1d1d1f] text-white rounded-lg text-[13px] hover:bg-[#3a3a3c] transition-colors disabled:opacity-40"
            onClick={handleUrlSubmit}
            disabled={isUploading || !urlText.trim()}
          >
            Index URLs (Unlimited Crawl)
          </button>

          {uploadStatus ? (
            <p className="mt-3 text-[12px] text-[#1d1d1f]">{uploadStatus}</p>
          ) : null}
        </div>

        <div className="px-5 py-4">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-medium text-[#1d1d1f]">Feedback</span>
            <ChevronRight className="w-4 h-4 text-[#86868b]" />
          </div>
        </div>
      </div>
    </div>
  );
}
