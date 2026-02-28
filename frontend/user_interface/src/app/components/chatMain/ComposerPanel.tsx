import { Send, X } from "lucide-react";
import type { ChangeEvent, RefObject } from "react";
import { AccessModeDropdown } from "../AccessModeDropdown";
import { ComposerQuickActionsCard } from "../ComposerQuickActionsCard";
import type { ComposerAttachment } from "./types";

type ComposerPanelProps = {
  accessMode: "restricted" | "full_access";
  agentControlsVisible: boolean;
  agentMode: "ask" | "company_agent";
  attachments: ComposerAttachment[];
  clearAttachments: () => void;
  enableAgentMode: () => void;
  enableDeepResearch: () => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
  isSending: boolean;
  isUploading: boolean;
  latestHighlightSnippets: string[];
  message: string;
  messageActionStatus: string;
  onAccessModeChange: (mode: "restricted" | "full_access") => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
  pasteHighlightsToComposer: () => void;
  setMessage: (value: string) => void;
  submit: () => Promise<void>;
};

function ComposerPanel({
  accessMode,
  agentControlsVisible,
  agentMode,
  attachments,
  clearAttachments,
  enableAgentMode,
  enableDeepResearch,
  fileInputRef,
  isSending,
  isUploading,
  latestHighlightSnippets,
  message,
  messageActionStatus,
  onAccessModeChange,
  onFileChange,
  pasteHighlightsToComposer,
  setMessage,
  submit,
}: ComposerPanelProps) {
  return (
    <div className="border-t border-black/[0.06] bg-white">
      <div className="mx-auto w-full max-w-[1800px] px-6 py-4">
        <div className="assistantComposer rounded-[22px] border border-black/[0.08] bg-[#f3f3f5]">
          <div className="assistantComposerInputShell rounded-[14px] border border-black/[0.08] bg-white">
            <input
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Ask for follow-up changes"
              className="assistantComposerInput min-w-0 flex-1 border-0 bg-transparent text-[15px] text-[#1d1d1f] placeholder:text-[#86868b] focus:outline-none"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void submit();
                }
              }}
            />
          </div>

          <div className="assistantComposerToolbar">
            <div className="assistantComposerTools">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(event) => {
                  void onFileChange(event);
                }}
              />
              <ComposerQuickActionsCard
                onUploadFile={() => fileInputRef.current?.click()}
                onSelectAgent={enableAgentMode}
                onSelectDeepResearch={enableDeepResearch}
                onPasteHighlights={pasteHighlightsToComposer}
                canPasteHighlights={latestHighlightSnippets.length > 0}
                disableUpload={isUploading || isSending}
                triggerClassName="composerAttachButton inline-flex items-center justify-center rounded-full border border-black/[0.08] bg-white text-[#6e6e73] shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors duration-150 hover:bg-[#f7f7f8] hover:text-[#1d1d1f] disabled:opacity-40"
              />

              <div className="assistantComposerAccessSlot">
                <div
                  className="accessReveal"
                  data-visible={agentControlsVisible && agentMode === "company_agent" ? "true" : "false"}
                >
                  {agentControlsVisible && agentMode === "company_agent" ? (
                    <AccessModeDropdown
                      value={accessMode}
                      onChange={(value) => onAccessModeChange(value)}
                    />
                  ) : (
                    <span className="accessPopupPlaceholder" aria-hidden="true" />
                  )}
                </div>
              </div>

              {attachments.length > 0 ? (
                <button
                  type="button"
                  onClick={clearAttachments}
                  className="inline-flex h-7 items-center gap-1 rounded-full border border-black/[0.08] bg-white px-2 text-[11px] text-[#1d1d1f]"
                  title="Clear attached files"
                >
                  <span>{attachments.length}</span>
                  <X className="h-3 w-3 text-[#86868b]" />
                </button>
              ) : null}
            </div>

            <div className="assistantComposerActions">
              <button
                type="button"
                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-black/[0.08] bg-[#a4a4aa] text-white shadow-[0_6px_14px_-12px_rgba(0,0,0,0.45)] transition-colors duration-150 hover:bg-[#98989e] disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!message.trim() || isSending || isUploading}
                onClick={() => void submit()}
                aria-label="Send message"
                title="Send"
              >
                <Send className="h-4.5 w-4.5" />
              </button>
            </div>
          </div>
        </div>
        {messageActionStatus ? (
          <div className="pointer-events-none fixed bottom-5 right-6 z-[120]">
            <div className="rounded-xl border border-black/[0.08] bg-white/95 px-3 py-2 text-[12px] text-[#4c4c50] shadow-[0_16px_34px_-24px_rgba(0,0,0,0.55)] backdrop-blur">
              {messageActionStatus}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export { ComposerPanel };
