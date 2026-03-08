import {
  Check,
  FileText,
  Globe,
  Link2,
  Loader2,
  PencilLine,
  Trash2,
  X,
} from "lucide-react";

import type { ProjectEvidenceItem, ProjectEvidenceState } from "./projectEvidenceHelpers";

type EvidenceProject = {
  id: string;
  name: string;
};

type ProjectEvidenceModalProps = {
  evidenceProject: EvidenceProject | null;
  evidenceProjectId: string;
  evidenceProjectState: ProjectEvidenceState;
  evidenceProjectUploadBusy: boolean;
  evidenceProjectUploadStatus: string;
  evidenceProjectUrlDraft: string;
  editingEvidenceKey: string | null;
  editingEvidenceDraft: string;
  evidenceActionBusyByKey: Record<string, boolean>;
  fileInputRef: (node: HTMLInputElement | null) => void;
  getEvidenceDisplayLabel: (item: ProjectEvidenceItem) => string;
  onClose: () => void;
  onRefresh: () => void;
  onStartRenameEvidenceItem: (item: ProjectEvidenceItem) => void;
  onCancelRenameEvidenceItem: () => void;
  onCommitRenameEvidenceItem: (item: ProjectEvidenceItem) => void;
  onEditingEvidenceDraftChange: (value: string) => void;
  onDeleteEvidenceItem: (item: ProjectEvidenceItem) => void;
  onProjectFileUpload: (files: FileList | null) => void;
  onProjectUrlDraftChange: (value: string) => void;
  onSubmitProjectUrls: () => void;
};

export function ProjectEvidenceModal({
  evidenceProject,
  evidenceProjectId,
  evidenceProjectState,
  evidenceProjectUploadBusy,
  evidenceProjectUploadStatus,
  evidenceProjectUrlDraft,
  editingEvidenceKey,
  editingEvidenceDraft,
  evidenceActionBusyByKey,
  fileInputRef,
  getEvidenceDisplayLabel,
  onClose,
  onRefresh,
  onStartRenameEvidenceItem,
  onCancelRenameEvidenceItem,
  onCommitRenameEvidenceItem,
  onEditingEvidenceDraftChange,
  onDeleteEvidenceItem,
  onProjectFileUpload,
  onProjectUrlDraftChange,
  onSubmitProjectUrls,
}: ProjectEvidenceModalProps) {
  if (!evidenceProject) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center p-5"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`Project sources for ${evidenceProject.name}`}
    >
      <div className="absolute inset-0 bg-black/35" />
      <div
        className="relative z-[121] w-full max-w-[980px] max-h-[86vh] rounded-2xl border border-black/[0.1] bg-white shadow-[0_24px_60px_rgba(0,0,0,0.28)] flex flex-col overflow-hidden"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-black/[0.08] flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[16px] font-semibold text-[#1d1d1f] truncate">{evidenceProject.name} sources</p>
            <p className="text-[12px] text-[#6e6e73] mt-0.5">Chats in project: {evidenceProjectState.projectChatCount}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onRefresh}
              className="h-8 px-3 rounded-lg border border-black/[0.08] text-[12px] text-[#1d1d1f] hover:bg-[#f5f5f7] transition-colors disabled:opacity-50"
              disabled={evidenceProjectState.status === "loading"}
              title="Refresh source list"
            >
              {evidenceProjectState.status === "loading" ? "Refreshing..." : "Refresh"}
            </button>
            <button
              onClick={onClose}
              className="h-8 w-8 rounded-lg border border-black/[0.08] text-[#6e6e73] hover:text-[#1d1d1f] hover:bg-[#f5f5f7] transition-colors inline-flex items-center justify-center"
              title="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {evidenceProjectState.status === "loading" ? (
            <div className="inline-flex items-center gap-2 text-[13px] text-[#6e6e73]">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Collecting sources used in this project's chats...</span>
            </div>
          ) : null}

          {evidenceProjectState.status === "error" ? (
            <p className="text-[13px] text-[#d44848]">{evidenceProjectState.errorMessage}</p>
          ) : null}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <section className="rounded-xl border border-black/[0.08] bg-[#fbfbfc] p-3">
              <div className="flex items-center justify-between">
                <div className="inline-flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-[#6e6e73]" />
                  <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-[#6e6e73]">Documents</p>
                </div>
                <span className="text-[12px] text-[#8d8d93]">{evidenceProjectState.documents.length}</span>
              </div>
              {evidenceProjectState.documents.length ? (
                <div className="mt-2 max-h-[240px] overflow-y-auto space-y-1.5 pr-1">
                  {evidenceProjectState.documents.map((item) => (
                    <div
                      key={item.key}
                      className="group rounded-lg border border-black/[0.05] bg-white px-2.5 py-2 hover:border-black/[0.14] transition-colors"
                    >
                      <div className="flex items-center gap-2 w-full">
                        {editingEvidenceKey === item.key ? (
                          <>
                            <input
                              value={editingEvidenceDraft}
                              onChange={(event) => onEditingEvidenceDraftChange(event.target.value)}
                              onKeyDown={(event) => {
                                if (event.key === "Enter") {
                                  event.preventDefault();
                                  onCommitRenameEvidenceItem(item);
                                }
                                if (event.key === "Escape") {
                                  event.preventDefault();
                                  onCancelRenameEvidenceItem();
                                }
                              }}
                              className="flex-1 h-7 px-2 rounded-md border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] focus:outline-none focus:ring-2 focus:ring-black/10"
                            />
                            <button
                              onClick={() => onCommitRenameEvidenceItem(item)}
                              className="p-1 rounded-md text-[#1d1d1f] hover:bg-black/5"
                              title="Save name"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={onCancelRenameEvidenceItem}
                              className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f]"
                              title="Cancel rename"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </>
                        ) : (
                          <>
                            <div className="inline-flex items-center gap-1.5 min-w-0 flex-1">
                              <FileText className="w-3.5 h-3.5 shrink-0 text-[#6e6e73]" />
                              <p className="text-[12px] text-[#1d1d1f] truncate" title={getEvidenceDisplayLabel(item)}>
                                {getEvidenceDisplayLabel(item)}
                              </p>
                            </div>
                            <div className="ml-1 inline-flex items-center gap-1 opacity-0 pointer-events-none transition-opacity duration-150 group-hover:opacity-100 group-hover:pointer-events-auto group-focus-within:opacity-100 group-focus-within:pointer-events-auto">
                              <button
                                onClick={() => onStartRenameEvidenceItem(item)}
                                className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f]"
                                title="Rename source"
                              >
                                <PencilLine className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => onDeleteEvidenceItem(item)}
                                disabled={
                                  Boolean(evidenceActionBusyByKey[item.key]) ||
                                  (item.fileIds.length === 0 &&
                                    !(item.type === "url" && String(item.href || item.label || "").trim()))
                                }
                                className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] disabled:opacity-45 disabled:cursor-not-allowed"
                                title={
                                  item.fileIds.length === 0 &&
                                  !(item.type === "url" && String(item.href || item.label || "").trim())
                                    ? "Delete unavailable for this source"
                                    : "Delete source"
                                }
                              >
                                {Boolean(evidenceActionBusyByKey[item.key]) ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <Trash2 className="w-3.5 h-3.5" />
                                )}
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                      <p className="text-[11px] text-[#8d8d93]">
                        {item.usageCount <= 0 && item.chatCount <= 0
                          ? "available source"
                          : `used ${item.usageCount}x in ${item.chatCount} chat${item.chatCount === 1 ? "" : "s"}`}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-[12px] text-[#8d8d93]">No documents or uploads yet.</p>
              )}
            </section>

            <section className="rounded-xl border border-black/[0.08] bg-[#fbfbfc] p-3">
              <div className="flex items-center justify-between">
                <div className="inline-flex items-center gap-1.5">
                  <Globe className="w-3.5 h-3.5 text-[#6e6e73]" />
                  <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-[#6e6e73]">URLs</p>
                </div>
                <span className="text-[12px] text-[#8d8d93]">{evidenceProjectState.urls.length}</span>
              </div>
              {evidenceProjectState.urls.length ? (
                <div className="mt-2 max-h-[240px] overflow-y-auto space-y-1.5 pr-1">
                  {evidenceProjectState.urls.map((item) => (
                    <div
                      key={item.key}
                      className="group block rounded-lg border border-black/[0.05] bg-white px-2.5 py-2 hover:border-black/[0.14] transition-colors"
                      title={item.href || item.label}
                    >
                      <div className="flex items-center gap-2 w-full">
                        {editingEvidenceKey === item.key ? (
                          <>
                            <input
                              value={editingEvidenceDraft}
                              onChange={(event) => onEditingEvidenceDraftChange(event.target.value)}
                              onKeyDown={(event) => {
                                if (event.key === "Enter") {
                                  event.preventDefault();
                                  onCommitRenameEvidenceItem(item);
                                }
                                if (event.key === "Escape") {
                                  event.preventDefault();
                                  onCancelRenameEvidenceItem();
                                }
                              }}
                              className="flex-1 h-7 px-2 rounded-md border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] focus:outline-none focus:ring-2 focus:ring-black/10"
                            />
                            <button
                              onClick={() => onCommitRenameEvidenceItem(item)}
                              className="p-1 rounded-md text-[#1d1d1f] hover:bg-black/5"
                              title="Save name"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={onCancelRenameEvidenceItem}
                              className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f]"
                              title="Cancel rename"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </>
                        ) : (
                          <>
                            <a href={item.href || "#"} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1.5 min-w-0 flex-1">
                              <Link2 className="w-3.5 h-3.5 shrink-0 text-[#6e6e73]" />
                              <p className="text-[12px] text-[#1d1d1f] truncate" title={getEvidenceDisplayLabel(item)}>
                                {getEvidenceDisplayLabel(item)}
                              </p>
                            </a>
                            <div className="ml-1 inline-flex items-center gap-1 opacity-0 pointer-events-none transition-opacity duration-150 group-hover:opacity-100 group-hover:pointer-events-auto group-focus-within:opacity-100 group-focus-within:pointer-events-auto">
                              <button
                                onClick={() => onStartRenameEvidenceItem(item)}
                                className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f]"
                                title="Rename source"
                              >
                                <PencilLine className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => onDeleteEvidenceItem(item)}
                                disabled={
                                  Boolean(evidenceActionBusyByKey[item.key]) ||
                                  (item.fileIds.length === 0 &&
                                    !(item.type === "url" && String(item.href || item.label || "").trim()))
                                }
                                className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] disabled:opacity-45 disabled:cursor-not-allowed"
                                title={
                                  item.fileIds.length === 0 &&
                                  !(item.type === "url" && String(item.href || item.label || "").trim())
                                    ? "Delete unavailable for this source"
                                    : "Delete source"
                                }
                              >
                                {Boolean(evidenceActionBusyByKey[item.key]) ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <Trash2 className="w-3.5 h-3.5" />
                                )}
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                      <p className="text-[11px] text-[#8d8d93]">
                        used {item.usageCount}x in {item.chatCount} chat
                        {item.chatCount === 1 ? "" : "s"}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-[12px] text-[#8d8d93]">No website sources used yet.</p>
              )}
            </section>
          </div>

          <section className="rounded-xl border border-black/[0.08] bg-[#fbfbfc] p-3 space-y-2.5">
            <p className="text-[12px] font-semibold text-[#1d1d1f]">Upload more sources</p>
            <input
              id={`project-file-input-${evidenceProjectId}`}
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => {
                onProjectFileUpload(event.target.files);
                event.currentTarget.value = "";
              }}
            />
            <div className="flex items-center gap-2">
              <label
                htmlFor={`project-file-input-${evidenceProjectId}`}
                className={`inline-flex h-8 cursor-pointer items-center rounded-lg border border-black/[0.08] px-3 text-[12px] text-[#1d1d1f] transition-colors hover:bg-white ${evidenceProjectUploadBusy ? "pointer-events-none opacity-50" : ""}`}
              >
                Upload files
              </label>
            </div>
            <textarea
              value={evidenceProjectUrlDraft}
              onChange={(event) => onProjectUrlDraftChange(event.target.value)}
              rows={3}
              placeholder="Paste one or more URLs"
              className="w-full rounded-lg border border-black/[0.08] bg-white px-2.5 py-2 text-[12px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
            />
            <div className="flex items-center gap-2">
              <button
                onClick={onSubmitProjectUrls}
                disabled={evidenceProjectUploadBusy || !evidenceProjectUrlDraft.trim()}
                className="h-8 px-3 rounded-lg bg-[#1d1d1f] text-white text-[12px] hover:bg-[#343438] transition-colors disabled:opacity-50"
              >
                Index URLs
              </button>
            </div>
            {evidenceProjectUploadStatus ? <p className="text-[12px] text-[#6e6e73]">{evidenceProjectUploadStatus}</p> : null}
            <p className="text-[11px] text-[#8d8d93]">Rename updates the display label in your workspace.</p>
            <p className="text-[11px] text-[#8d8d93]">Uploaded sources become available for future chats in this project.</p>
          </section>
        </div>
      </div>
    </div>
  );
}
