import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Copy, Download, Eye, FileText, Loader2, PenSquare } from "lucide-react";

import { updateCanvasDocument } from "../../../api/client";
import type { CanvasDocumentRecord } from "../../messageBlocks";
import { useCanvasStore } from "../../stores/canvasStore";
import type { CitationFocus } from "../../types";
import { renderMathInMarkdown, renderRichText } from "../../utils/richText";
import { useCitationAnchorBinding } from "../infoPanel/useCitationAnchorBinding";

type CanvasWorkspaceSurfaceProps = {
  documentId: string;
  fallbackDocument?: CanvasDocumentRecord | null;
  onSelectCitationFocus?: (citation: CitationFocus) => void;
  embedded?: boolean;
};

function CanvasWorkspaceSurface({
  documentId,
  fallbackDocument = null,
  onSelectCitationFocus,
  embedded = false,
}: CanvasWorkspaceSurfaceProps) {
  const documentsById = useCanvasStore((state) => state.documentsById);
  const upsertDocuments = useCanvasStore((state) => state.upsertDocuments);
  const updateDocumentContent = useCanvasStore((state) => state.updateDocumentContent);
  const markDocumentSaved = useCanvasStore((state) => state.markDocumentSaved);
  const activeDocument =
    (documentId ? documentsById[documentId] || null : null) ||
    (fallbackDocument ? { ...fallbackDocument, isDirty: false } : null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveMessage, setSaveMessage] = useState("");
  const [copying, setCopying] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [surface, setSurface] = useState<"preview" | "edit">("preview");
  const previewRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!fallbackDocument?.id) {
      return;
    }
    upsertDocuments([fallbackDocument]);
  }, [fallbackDocument, upsertDocuments]);

  const renderedPreviewHtml = useMemo(
    () => renderRichText(renderMathInMarkdown(String(activeDocument?.content || ""))),
    [activeDocument?.content],
  );

  useEffect(() => {
    const nextSurface =
      String(activeDocument?.modeVariant || "").trim().toLowerCase() === "rag" ? "preview" : "edit";
    setSurface(nextSurface);
  }, [activeDocument?.id, activeDocument?.modeVariant]);

  useCitationAnchorBinding({
    containerRef: previewRef,
    renderedInfoHtml: renderedPreviewHtml,
    userPrompt: String(activeDocument?.userPrompt || ""),
    assistantHtml: String(activeDocument?.content || ""),
    infoHtml: String(activeDocument?.infoHtml || ""),
    infoPanel:
      activeDocument?.infoPanel && typeof activeDocument.infoPanel === "object"
        ? activeDocument.infoPanel
        : null,
    evidenceCards: [],
    onSelectCitationFocus,
  });

  const saveDocument = useCallback(
    async (reason: "manual" | "blur") => {
      if (!activeDocument || !activeDocument.id || !activeDocument.isDirty) {
        return;
      }
      setSaveState("saving");
      setSaveMessage("");
      try {
        const saved = await updateCanvasDocument(activeDocument.id, {
          title: activeDocument.title,
          content: activeDocument.content,
        });
        markDocumentSaved(activeDocument.id, String(saved?.content ?? activeDocument.content));
        setSaveState("saved");
        setSaveMessage(reason === "blur" ? "Auto-saved." : "Saved.");
      } catch (error) {
        setSaveState("error");
        setSaveMessage(`Save failed: ${String(error)}`);
      }
    },
    [activeDocument, markDocumentSaved],
  );

  useEffect(() => {
    setSaveState("idle");
    setSaveMessage("");
  }, [activeDocument?.id]);

  useEffect(() => {
    if (activeDocument?.isDirty && saveState === "saved") {
      setSaveState("idle");
      setSaveMessage("");
    }
  }, [activeDocument?.isDirty, saveState]);

  const copyMarkdown = useCallback(async () => {
    if (!activeDocument?.content) {
      setSaveState("error");
      setSaveMessage("Nothing to copy.");
      return;
    }
    setCopying(true);
    try {
      if (!navigator?.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable.");
      }
      await navigator.clipboard.writeText(activeDocument.content);
      setSaveState("saved");
      setSaveMessage("Copied markdown.");
    } catch (error) {
      setSaveState("error");
      setSaveMessage(`Copy failed: ${String(error)}`);
    } finally {
      setCopying(false);
    }
  }, [activeDocument?.content]);

  const downloadMarkdown = useCallback(() => {
    if (!activeDocument?.content) {
      setSaveState("error");
      setSaveMessage("Nothing to download.");
      return;
    }
    setDownloading(true);
    try {
      const filenameBase = String(activeDocument.title || "document")
        .trim()
        .replace(/[^\w\s-]/g, "")
        .replace(/\s+/g, "-")
        .toLowerCase();
      const filename = `${filenameBase || "document"}.md`;
      const blob = new Blob([activeDocument.content], { type: "text/markdown;charset=utf-8" });
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(objectUrl);
      setSaveState("saved");
      setSaveMessage(`Downloaded ${filename}.`);
    } catch (error) {
      setSaveState("error");
      setSaveMessage(`Download failed: ${String(error)}`);
    } finally {
      setDownloading(false);
    }
  }, [activeDocument?.content, activeDocument?.title]);

  if (!activeDocument) {
    return (
      <div className="rounded-[28px] border border-dashed border-black/[0.08] bg-white/70 px-5 py-6 text-center text-[13px] text-[#667085]">
        Canvas unavailable for this turn.
      </div>
    );
  }

  const shellClass = embedded
    ? "overflow-hidden rounded-[30px] border border-black/[0.08] bg-white shadow-[0_18px_48px_rgba(15,23,42,0.08)]"
    : "flex min-h-0 flex-1 flex-col overflow-hidden rounded-[30px] border border-black/[0.08] bg-white shadow-[0_18px_48px_rgba(15,23,42,0.08)]";
  const bodyClass = embedded ? "px-5 pb-5" : "min-h-0 flex-1 px-6 pb-6";
  const previewClass = embedded
    ? "chat-answer-html assistantAnswerBody max-h-[760px] overflow-y-auto rounded-[24px] border border-black/[0.06] bg-[#fbfbfd] px-5 py-4"
    : "chat-answer-html assistantAnswerBody min-h-0 flex-1 overflow-y-auto rounded-[24px] border border-black/[0.06] bg-[#fbfbfd] px-5 py-4";
  const editClass = embedded
    ? "h-[560px] w-full resize-none rounded-[24px] border border-black/[0.06] bg-[#fbfbfd] px-5 py-4 font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[13px] leading-6 text-[#111827] outline-none transition focus:border-[#98a2b3] focus:ring-2 focus:ring-[#dbeafe]"
    : "min-h-0 flex-1 resize-none rounded-[24px] border border-black/[0.06] bg-[#fbfbfd] px-5 py-4 font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[13px] leading-6 text-[#111827] outline-none transition focus:border-[#98a2b3] focus:ring-2 focus:ring-[#dbeafe]";

  return (
    <section className={shellClass}>
      <div className="border-b border-black/[0.06] px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#111827] text-white shadow-[0_10px_30px_rgba(17,24,39,0.18)]">
              <FileText className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <h4 className="truncate text-[18px] font-semibold tracking-[-0.02em] text-[#111827]">
                {activeDocument.title || "Canvas draft"}
              </h4>
              <p className="mt-1 text-[12px] text-[#667085]">
                {surface === "preview"
                  ? "Structured cited workspace. Click citations to open PDF evidence in the right panel."
                  : "Editable markdown workspace. Save or auto-save on blur."}
              </p>
              {saveMessage ? (
                <p className={`mt-1 text-[11px] ${saveState === "error" ? "text-[#b42318]" : "text-[#667085]"}`}>
                  {saveMessage}
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <div className="inline-flex items-center rounded-full border border-black/[0.08] bg-[#f8fafc] p-1 shadow-sm">
              <button
                type="button"
                onClick={() => setSurface("preview")}
                className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-[12px] font-semibold transition ${
                  surface === "preview" ? "bg-[#111827] text-white" : "text-[#667085]"
                }`}
              >
                <Eye className="h-3.5 w-3.5" />
                Preview
              </button>
              <button
                type="button"
                onClick={() => setSurface("edit")}
                className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-[12px] font-semibold transition ${
                  surface === "edit" ? "bg-[#111827] text-white" : "text-[#667085]"
                }`}
              >
                <PenSquare className="h-3.5 w-3.5" />
                Edit
              </button>
            </div>
            <button
              type="button"
              onClick={() => void copyMarkdown()}
              disabled={!activeDocument.content || copying || saveState === "saving"}
              className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.1] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1f2937] transition hover:border-black/[0.24] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Copy className="h-3.5 w-3.5" />
              {copying ? "Copying..." : "Copy"}
            </button>
            <button
              type="button"
              onClick={downloadMarkdown}
              disabled={!activeDocument.content || downloading || saveState === "saving"}
              className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.1] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1f2937] transition hover:border-black/[0.24] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Download className="h-3.5 w-3.5" />
              {downloading ? "Preparing..." : "Download"}
            </button>
            <button
              type="button"
              onClick={() => void saveDocument("manual")}
              disabled={!activeDocument.isDirty || saveState === "saving"}
              className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.1] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1f2937] transition hover:border-black/[0.24] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saveState === "saving" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : saveState === "saved" && !activeDocument.isDirty ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-[#2f6a3f]" />
              ) : null}
              {saveState === "saving" ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </div>
      <div className={bodyClass}>
        {surface === "preview" ? (
          <div
            ref={previewRef}
            className={previewClass}
            dangerouslySetInnerHTML={{ __html: renderedPreviewHtml }}
          />
        ) : (
          <textarea
            value={activeDocument.content}
            onChange={(event) => updateDocumentContent(activeDocument.id, event.target.value)}
            onBlur={() => {
              void saveDocument("blur");
            }}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
                event.preventDefault();
                void saveDocument("manual");
              }
            }}
            className={editClass}
            spellCheck={false}
          />
        )}
      </div>
    </section>
  );
}

export { CanvasWorkspaceSurface };
