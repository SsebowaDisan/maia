import { InteractionOverlay } from "./InteractionOverlay";

type DocsSceneProps = {
  activeDetail: string;
  activeEventType: string;
  activeTitle: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
  docBodyHtml: string;
  docBodyPreview: string;
  docsFrameUrl: string;
  sceneText: string;
  scrollDirection: string;
  scrollPercent: number | null;
};

function DocsScene({
  activeDetail,
  activeEventType,
  activeTitle,
  action,
  actionPhase,
  actionStatus,
  actionTargetLabel,
  docBodyHtml,
  docBodyPreview,
  docsFrameUrl,
  sceneText,
  scrollDirection,
  scrollPercent,
}: DocsSceneProps) {
  const isTyping = action === "type" && actionStatus !== "failed";
  const typingPulse = isTyping && (actionPhase === "active" || actionPhase === "start");
  return (
    <div className="absolute inset-0 bg-[linear-gradient(180deg,#ededf0_0%,#e3e4e8_100%)] p-3 text-[#1d1d1f]">
      <div className="h-full w-full overflow-hidden rounded-[18px] border border-black/[0.08] bg-white shadow-[0_26px_60px_-40px_rgba(0,0,0,0.55)]">
        <div className="flex items-center gap-2 border-b border-black/[0.08] px-3 py-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <span className="ml-2 text-[12px] font-semibold tracking-tight text-[#3a3a3c]">
            Google Docs
          </span>
          {docsFrameUrl ? (
            <span className="ml-2 max-w-[65%] truncate rounded-full border border-black/[0.08] bg-[#f7f7f9] px-2.5 py-0.5 text-[10px] text-[#4c4c50]">
              {docsFrameUrl}
            </span>
          ) : null}
        </div>
        <div className="relative h-[calc(100%-42px)] bg-[#f3f3f5]">
          <InteractionOverlay
            sceneSurface="google_docs"
            activeEventType={activeEventType}
            activeDetail={activeDetail}
            scrollDirection={scrollDirection}
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
          />
          {docsFrameUrl ? (
            <>
              <iframe
                src={docsFrameUrl}
                title="Google Docs live preview"
                className="h-full w-full border-0 bg-white"
                sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                referrerPolicy="no-referrer-when-downgrade"
              />
              {typingPulse ? (
                <div className="pointer-events-none absolute bottom-4 left-4 right-4 rounded-lg border border-black/20 bg-black/5 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#1d1d1f]">
                  Typing focus active
                </div>
              ) : null}
            </>
          ) : (
            <div className="h-full p-5">
              <div
                className={`mx-auto h-full w-[96%] max-w-[1120px] rounded-xl border bg-white px-8 py-6 transition-all duration-300 ${
                  typingPulse
                    ? "border-black/25 shadow-[0_0_0_1px_rgba(0,0,0,0.18)]"
                    : "border-black/[0.08]"
                }`}
              >
                <div className="mb-4 border-b border-black/[0.06] pb-3">
                  <p className="text-[18px] font-semibold text-[#202024]">
                    {activeTitle || "Research Notes"}
                  </p>
                  <p className="mt-1 text-[12px] text-[#6e6e73]">
                    {sceneText || activeDetail || "Preparing and writing structured document content."}
                  </p>
                </div>
                <div className="h-[calc(100%-68px)] overflow-y-auto pr-1">
                  {docBodyPreview ? (
                    <div
                      className="[&_h1]:mb-2 [&_h1]:text-[22px] [&_h1]:font-semibold [&_h2]:mb-1.5 [&_h2]:text-[18px] [&_h2]:font-semibold [&_h3]:mb-1 [&_h3]:text-[15px] [&_h3]:font-semibold [&_p]:mb-1.5 [&_ul]:mb-1.5 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:mb-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-[#f2f2f7] [&_code]:px-1 [&_code]:py-0.5 text-[13px] leading-[1.65] text-[#232327]"
                      dangerouslySetInnerHTML={{ __html: docBodyHtml }}
                    />
                  ) : (
                    <p className="text-[13px] text-[#4c4c50]">Preparing document...</p>
                  )}
                  <span className="inline-block h-[14px] w-[1px] animate-pulse bg-[#1f1f22]" />
                </div>
              </div>
            </div>
          )}
          {typeof scrollPercent === "number" ? (
            <div className="pointer-events-none absolute right-2 top-16 bottom-4 flex flex-col items-center">
              <div className="h-full w-1.5 rounded-full bg-black/15">
                <div
                  className="w-1.5 rounded-full bg-black/45 transition-all duration-300"
                  style={{ height: "20px", marginTop: `calc(${scrollPercent}% - 10px)` }}
                />
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export { DocsScene };
