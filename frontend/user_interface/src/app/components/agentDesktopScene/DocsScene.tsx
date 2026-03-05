type DocsSceneProps = {
  activeDetail: string;
  activeTitle: string;
  docBodyHtml: string;
  docBodyPreview: string;
  docBodyScrollRef: React.RefObject<HTMLDivElement | null>;
  docsFrameUrl: string;
  sceneText: string;
};

function DocsScene({
  activeDetail,
  activeTitle,
  docBodyHtml,
  docBodyPreview,
  docBodyScrollRef,
  docsFrameUrl,
  sceneText,
}: DocsSceneProps) {
  return (
    <div className="absolute inset-0 bg-[linear-gradient(180deg,#e8eaef_0%,#dde1ea_100%)] p-3 text-[#1d1d1f]">
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
        <div className="relative h-[calc(100%-42px)] bg-[#f5f6f8]">
          {docsFrameUrl ? (
            <iframe
              src={docsFrameUrl}
              title="Google Docs live preview"
              className="h-full w-full border-0 bg-white"
              sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
              referrerPolicy="no-referrer-when-downgrade"
            />
          ) : (
            <div className="h-full p-5">
              <div className="mx-auto h-full w-[96%] max-w-[1120px] rounded-xl border border-black/[0.08] bg-white px-8 py-6">
                <p className="text-[18px] font-semibold text-[#202024]">
                  {activeTitle || "Execution Plan & Notes"}
                </p>
                <p className="mt-1 text-[12px] text-[#6e6e73]">
                  {sceneText || activeDetail || "Writing planning blueprint and findings to Google Docs."}
                </p>
                <div className="mt-4 space-y-3">
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
          {docBodyPreview ? (
            <div className="pointer-events-none absolute right-3 bottom-3 z-10 w-[min(42%,460px)] rounded-lg border border-black/[0.08] bg-white/88 px-3 py-2 shadow-[0_8px_18px_-16px_rgba(0,0,0,0.55)] backdrop-blur-sm">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">
                Live docs typing
              </p>
              <div
                ref={docBodyScrollRef}
                className="mt-1.5 max-h-[124px] overflow-y-auto rounded-md border border-black/[0.06] bg-white px-2.5 py-2 text-[12px] leading-[1.55] text-[#1f1f22]"
              >
                <div
                  className="[&_h1]:mb-2 [&_h1]:text-[17px] [&_h1]:font-semibold [&_h2]:mb-1.5 [&_h2]:text-[15px] [&_h2]:font-semibold [&_h3]:mb-1 [&_h3]:text-[13px] [&_h3]:font-semibold [&_p]:mb-1.5 [&_ul]:mb-1.5 [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:mb-1.5 [&_ol]:list-decimal [&_ol]:pl-4 [&_code]:rounded [&_code]:bg-[#f2f2f7] [&_code]:px-1 [&_code]:py-0.5"
                  dangerouslySetInnerHTML={{ __html: docBodyHtml }}
                />
                <span className="inline-block h-[12px] w-[1px] animate-pulse bg-[#1f1f22]" />
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export { DocsScene };
