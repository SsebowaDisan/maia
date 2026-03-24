import { AlertCircle, FileText, Folder, Loader2, X } from "lucide-react";
import type { ComposerAttachment } from "../types";

type ComposerAttachmentChipsProps = {
  attachments: ComposerAttachment[];
  isSending: boolean;
  onClearAttachments: () => void;
  onOpenPreview: (attachment: ComposerAttachment) => void;
  onRemoveAttachment: (attachmentId: string) => void;
  attachmentStatusLabel: (attachment: ComposerAttachment) => string;
};

function ComposerAttachmentChips({
  attachments,
  isSending,
  onClearAttachments,
  onOpenPreview,
  onRemoveAttachment,
  attachmentStatusLabel,
}: ComposerAttachmentChipsProps) {
  if (!attachments.length) {
    return null;
  }

  const visibleAttachments = attachments.slice(0, 3);
  const hiddenAttachmentCount = Math.max(0, attachments.length - visibleAttachments.length);

  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 pr-1">
        {visibleAttachments.map((attachment) => (
          <div
            key={attachment.id}
            className="inline-flex h-7 min-w-0 max-w-full items-center rounded-full border border-black/[0.08] bg-white text-[11px] text-[#1d1d1f] shadow-[0_1px_2px_rgba(0,0,0,0.04)] sm:max-w-[260px]"
            title={attachment.message ? `${attachment.name} - ${attachment.message}` : attachment.name}
          >
            {(() => {
              const attachmentStatus = attachmentStatusLabel(attachment);
              const content = (
                <>
                  {attachment.status === "uploading" || attachment.status === "indexing" ? (
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[#6e6e73]" />
                  ) : attachment.status === "error" ? (
                    <AlertCircle className="h-3.5 w-3.5 shrink-0 text-[#d44848]" />
                  ) : attachment.kind === "project" ? (
                    <Folder className="h-3.5 w-3.5 shrink-0 text-[#6e6e73]" />
                  ) : (
                    <FileText className="h-3.5 w-3.5 shrink-0 text-[#6e6e73]" />
                  )}
                  <span className="min-w-0 flex-1 truncate">{attachment.name}</span>
                  {attachmentStatus ? (
                    <span className="max-w-[84px] shrink truncate text-[10px] text-[#8d8d93] md:max-w-[108px]">
                      {attachmentStatus}
                    </span>
                  ) : null}
                </>
              );

              if (attachment.localUrl || attachment.fileId) {
                return (
                  <button
                    type="button"
                    onClick={() => onOpenPreview(attachment)}
                    className="inline-flex min-w-0 flex-1 items-center gap-1.5 rounded-l-full px-2.5 py-1 transition-colors duration-150 hover:bg-[#f7f7f8]"
                  >
                    {content}
                  </button>
                );
              }

              return (
                <div className="inline-flex min-w-0 flex-1 items-center gap-1.5 rounded-l-full px-2.5 py-1">
                  {content}
                </div>
              );
            })()}
            <button
              type="button"
              onClick={() => onRemoveAttachment(attachment.id)}
              disabled={isSending}
              className="inline-flex h-7 w-8 shrink-0 items-center justify-center rounded-r-full text-[#8d8d93] transition-colors duration-150 hover:bg-[#f7f7f8] hover:text-[#1d1d1f] disabled:opacity-50"
              aria-label={`Remove ${attachment.name}`}
              title={`Remove ${attachment.name}`}
            >
              <X className="h-3 w-3 shrink-0" />
            </button>
          </div>
        ))}
        {hiddenAttachmentCount > 0 ? (
          <span className="inline-flex h-7 items-center rounded-full border border-black/[0.08] bg-white px-2.5 text-[11px] text-[#6e6e73]">
            +{hiddenAttachmentCount} more
          </span>
        ) : null}
      </div>

      {attachments.length > 1 ? (
        <button
          type="button"
          onClick={onClearAttachments}
          className="inline-flex h-7 shrink-0 items-center gap-1 rounded-full border border-black/[0.08] bg-white px-2.5 text-[11px] text-[#6e6e73] transition-colors duration-150 hover:bg-[#f7f7f8] hover:text-[#1d1d1f]"
          title="Clear all attachments"
        >
          <X className="h-3 w-3" />
          <span>Clear</span>
        </button>
      ) : null}
    </div>
  );
}

export { ComposerAttachmentChips };
