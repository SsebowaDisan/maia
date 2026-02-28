import type { DocumentHighlight } from "./types";

function highlightBackground(color: "yellow" | "green") {
  return color === "green" ? "rgba(112, 216, 123, 0.22)" : "rgba(255, 213, 79, 0.22)";
}

type DocumentPdfSceneProps = {
  documentHighlights: DocumentHighlight[];
  stageFileUrl: string;
};

function DocumentPdfScene({ documentHighlights, stageFileUrl }: DocumentPdfSceneProps) {
  return (
    <div className="absolute inset-0">
      <iframe
        src={`${stageFileUrl}#toolbar=0&navpanes=0&scrollbar=0`}
        title="Agent PDF live preview"
        className="absolute inset-0 h-full w-full bg-white"
      />
      {documentHighlights.length ? (
        <div className="pointer-events-none absolute left-3 right-3 bottom-3 rounded-xl border border-black/15 bg-white/85 px-3 py-2 text-[11px] text-[#1d1d1f] backdrop-blur-sm">
          <p className="text-[11px] font-semibold">Copied highlights</p>
          <div className="mt-1 space-y-1">
            {documentHighlights.map((item, index) => (
              <p key={`${item.word}-${index}`} className="line-clamp-2">
                <span
                  className="rounded px-1 py-0.5 font-semibold"
                  style={{ backgroundColor: highlightBackground(item.color) }}
                >
                  {item.word || "highlight"}
                </span>{" "}
                {item.snippet}
              </p>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

type DocumentFallbackSceneProps = {
  activeDetail: string;
  clipboardPreview: string;
  documentHighlights: DocumentHighlight[];
  sceneText: string;
  stageFileName: string;
};

function DocumentFallbackScene({
  activeDetail,
  clipboardPreview,
  documentHighlights,
  sceneText,
  stageFileName,
}: DocumentFallbackSceneProps) {
  return (
    <div className="absolute inset-0 px-4 py-3 text-white/85">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[12px] font-medium">{stageFileName}</span>
        <span className="text-[10px] uppercase tracking-[0.08em] text-white/65">editing</span>
      </div>
      <p className="mb-3 text-[11px] text-white/85">
        {sceneText || activeDetail || "Preparing and updating document blocks..."}
      </p>
      {documentHighlights.length ? (
        <div className="mb-3 space-y-1.5 rounded-lg border border-white/20 bg-white/10 px-2.5 py-2">
          {documentHighlights.map((item, index) => (
            <p key={`${item.word}-inline-${index}`} className="line-clamp-2 text-[10px] text-white/90">
              <span
                className="rounded px-1 py-0.5 font-semibold"
                style={{ backgroundColor: highlightBackground(item.color) }}
              >
                {item.word || "highlight"}
              </span>{" "}
              {item.snippet}
            </p>
          ))}
        </div>
      ) : null}
      {clipboardPreview ? (
        <div className="mb-3 rounded-lg border border-white/20 bg-white/10 px-2.5 py-1.5 text-[10px] text-white/90">
          Clipboard: {clipboardPreview}
        </div>
      ) : null}
      <div className="space-y-2">
        <div className="h-2 w-[88%] rounded-full bg-white/15" />
        <div className="h-2 w-[74%] rounded-full bg-white/10" />
        <div className="h-2 w-[91%] rounded-full bg-white/15" />
        <div className="h-2 w-[82%] rounded-full bg-white/10" />
        <div className="h-2 w-[66%] rounded-full bg-white/15" />
      </div>
    </div>
  );
}

export { DocumentFallbackScene, DocumentPdfScene };
