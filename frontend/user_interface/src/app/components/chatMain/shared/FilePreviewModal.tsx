import { ExternalLink, X } from "lucide-react";
import { useMemo } from "react";
import { buildRawFileUrl } from "../../../../api/client";
import type { FilePreviewAttachment } from "../types";

type FilePreviewModalProps = {
  attachment: FilePreviewAttachment | null;
  onClose: () => void;
  emptyPreviewMessage: string;
};

function isImagePreview(name: string, mimeType: string): boolean {
  return mimeType.startsWith("image/") || /\.(png|jpe?g|gif|bmp|webp|svg|tiff?)$/i.test(name);
}

function isPdfPreview(name: string, mimeType: string): boolean {
  return mimeType === "application/pdf" || name.endsWith(".pdf");
}

function FilePreviewModal({ attachment, onClose, emptyPreviewMessage }: FilePreviewModalProps) {
  const previewUrl = useMemo(() => {
    if (!attachment) {
      return "";
    }
    if (attachment.localUrl) {
      return attachment.localUrl;
    }
    if (attachment.fileId) {
      return buildRawFileUrl(attachment.fileId);
    }
    return "";
  }, [attachment]);

  const previewNameLower = String(attachment?.name || "").toLowerCase();
  const previewMime = String(attachment?.mimeType || "").toLowerCase();
  const previewIsImage = isImagePreview(previewNameLower, previewMime);
  const previewIsPdf = isPdfPreview(previewNameLower, previewMime);

  if (!attachment) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[140] bg-black/45 px-4 py-6 backdrop-blur-[2px]" onClick={onClose}>
      <div
        className="mx-auto flex h-full w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-[0_24px_70px_-28px_rgba(0,0,0,0.65)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-black/[0.06] px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-[14px] font-medium text-[#1d1d1f]" title={attachment.name}>
              {attachment.name}
            </p>
            {attachment.message ? (
              <p className="text-[12px] text-[#8d8d93]">{attachment.message}</p>
            ) : null}
          </div>
          <div className="ml-3 flex items-center gap-2">
            {previewUrl ? (
              <a
                href={previewUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-full border border-black/[0.1] px-3 py-1.5 text-[11px] text-[#1d1d1f] hover:bg-[#f5f5f7]"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Open
              </a>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.1] text-[#6e6e73] hover:bg-[#f5f5f7] hover:text-[#1d1d1f]"
              aria-label="Close preview"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-[#f5f5f7] p-4">
          {!previewUrl ? (
            <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-black/[0.12] bg-white text-[13px] text-[#6e6e73]">
              {emptyPreviewMessage}
            </div>
          ) : previewIsImage ? (
            <div className="flex min-h-full items-start justify-center">
              <img
                src={previewUrl}
                alt={attachment.name}
                className="h-auto max-w-full rounded-xl border border-black/[0.08] bg-white"
              />
            </div>
          ) : previewIsPdf ? (
            <iframe
              src={previewUrl}
              title={`Preview ${attachment.name}`}
              className="h-full min-h-[420px] w-full rounded-xl border border-black/[0.08] bg-white"
            />
          ) : (
            <iframe
              src={previewUrl}
              title={`Preview ${attachment.name}`}
              className="h-full min-h-[420px] w-full rounded-xl border border-black/[0.08] bg-white"
            />
          )}
        </div>
      </div>
    </div>
  );
}

export { FilePreviewModal };
