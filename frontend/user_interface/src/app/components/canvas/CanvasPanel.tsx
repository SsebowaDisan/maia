import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Copy, Download, FileText, Loader2 } from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../ui/sheet";
import { updateCanvasDocument } from "../../../api/client";
import { useCanvasStore } from "../../stores/canvasStore";

function CanvasPanel() {
  const isOpen = useCanvasStore((state) => state.isOpen);
  const activeDocumentId = useCanvasStore((state) => state.activeDocumentId);
  const documentsById = useCanvasStore((state) => state.documentsById);
  const closePanel = useCanvasStore((state) => state.closePanel);
  const updateDocumentContent = useCanvasStore((state) => state.updateDocumentContent);
  const markDocumentSaved = useCanvasStore((state) => state.markDocumentSaved);
  const activeDocument = activeDocumentId ? documentsById[activeDocumentId] || null : null;
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveMessage, setSaveMessage] = useState("");
  const [copying, setCopying] = useState(false);
  const [downloading, setDownloading] = useState(false);

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
        markDocumentSaved(
          activeDocument.id,
          String(saved?.content ?? activeDocument.content),
        );
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
  }, [activeDocumentId]);

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
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(activeDocument.content);
      } else {
        throw new Error("Clipboard API unavailable.");
      }
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

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && closePanel()}>
      <SheetContent
        side="right"
        className="w-[min(92vw,760px)] min-w-0 gap-0 border-l border-black/[0.08] bg-[#fbfbfd] p-0 sm:min-w-[380px] sm:max-w-[760px]"
      >
        <SheetHeader className="border-b border-black/[0.06] px-6 py-5">
          <div className="flex items-start justify-between gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#111827] text-white shadow-[0_10px_30px_rgba(17,24,39,0.18)]">
              <FileText className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <SheetTitle className="truncate text-[18px] font-semibold text-[#111827]">
                {activeDocument?.title || "Canvas draft"}
              </SheetTitle>
              <SheetDescription className="text-[12px] text-[#667085]">
                Draft in markdown. Changes save on blur or with the Save button.
              </SheetDescription>
              {saveMessage ? (
                <p
                  className={`mt-1 text-[11px] ${
                    saveState === "error" ? "text-[#b42318]" : "text-[#667085]"
                  }`}
                >
                  {saveMessage}
                </p>
              ) : null}
            </div>
            <div className="shrink-0 flex items-center gap-2">
              <button
                type="button"
                onClick={() => void copyMarkdown()}
                disabled={!activeDocument?.content || copying || saveState === "saving"}
                className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.1] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1f2937] transition hover:border-black/[0.24] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Copy className="h-3.5 w-3.5" />
                {copying ? "Copying..." : "Copy"}
              </button>
              <button
                type="button"
                onClick={downloadMarkdown}
                disabled={!activeDocument?.content || downloading || saveState === "saving"}
                className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.1] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1f2937] transition hover:border-black/[0.24] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Download className="h-3.5 w-3.5" />
                {downloading ? "Preparing..." : "Download"}
              </button>
              <button
                type="button"
                onClick={() => void saveDocument("manual")}
                disabled={!activeDocument?.isDirty || saveState === "saving"}
                className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.1] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1f2937] transition hover:border-black/[0.24] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saveState === "saving" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : saveState === "saved" && !activeDocument?.isDirty ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-[#2f6a3f]" />
                ) : null}
                {saveState === "saving" ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col px-6 py-5">
          {activeDocument ? (
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
              className="min-h-0 flex-1 resize-none rounded-[28px] border border-black/[0.08] bg-white px-5 py-4 font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[13px] leading-6 text-[#111827] shadow-[0_16px_40px_rgba(15,23,42,0.06)] outline-none transition focus:border-[#98a2b3] focus:ring-2 focus:ring-[#dbeafe]"
              spellCheck={false}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center rounded-[28px] border border-dashed border-black/[0.08] bg-white/70 text-center text-[13px] text-[#667085]">
              Select a document action from the chat to open a draft here.
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

export { CanvasPanel };
