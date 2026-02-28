type SheetsSceneProps = {
  activeDetail: string;
  sceneText: string;
  sheetPreviewRows: string[];
  sheetStatusLine: string;
  sheetsFrameUrl: string;
};

function SheetsScene({
  activeDetail,
  sceneText,
  sheetPreviewRows,
  sheetStatusLine,
  sheetsFrameUrl,
}: SheetsSceneProps) {
  return (
    <div className="absolute inset-0 bg-[linear-gradient(180deg,#e6e8ee_0%,#dce0e9_100%)] p-3 text-[#1d1d1f]">
      <div className="h-full w-full overflow-hidden rounded-[18px] border border-black/[0.08] bg-white shadow-[0_26px_60px_-40px_rgba(0,0,0,0.55)]">
        <div className="flex items-center gap-2 border-b border-black/[0.08] px-3 py-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <span className="ml-2 text-[12px] font-semibold tracking-tight text-[#3a3a3c]">
            Google Sheets
          </span>
          {sheetsFrameUrl ? (
            <span className="ml-2 max-w-[65%] truncate rounded-full border border-black/[0.08] bg-[#f7f7f9] px-2.5 py-0.5 text-[10px] text-[#4c4c50]">
              {sheetsFrameUrl}
            </span>
          ) : null}
        </div>
        <div className="relative h-[calc(100%-42px)] bg-[#f5f6f8]">
          {sheetsFrameUrl ? (
            <iframe
              src={sheetsFrameUrl}
              title="Google Sheets live preview"
              className="h-full w-full border-0 bg-white"
              sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
              referrerPolicy="no-referrer-when-downgrade"
            />
          ) : (
            <div className="h-full p-5">
              <div className="h-full rounded-xl border border-black/[0.08] bg-white">
                <div className="grid grid-cols-[120px_repeat(4,minmax(0,1fr))] border-b border-black/[0.06] bg-[#f8f9fc] text-[10px] font-semibold uppercase tracking-[0.08em] text-[#7b7b80]">
                  <div className="border-r border-black/[0.06] px-3 py-2">A</div>
                  <div className="border-r border-black/[0.06] px-3 py-2">B</div>
                  <div className="border-r border-black/[0.06] px-3 py-2">C</div>
                  <div className="border-r border-black/[0.06] px-3 py-2">D</div>
                  <div className="px-3 py-2">E</div>
                </div>
                <div className="space-y-0">
                  {sheetPreviewRows.length ? (
                    sheetPreviewRows.map((row, rowIndex) => (
                      <div
                        key={`sheet-row-${rowIndex}`}
                        className="grid grid-cols-[120px_repeat(4,minmax(0,1fr))] border-b border-black/[0.05] text-[12px] text-[#2a2a2d]"
                      >
                        <div className="border-r border-black/[0.05] px-3 py-2 text-[#6e6e73]">
                          {rowIndex + 1}
                        </div>
                        <div className="col-span-4 px-3 py-2 font-medium">{row}</div>
                      </div>
                    ))
                  ) : (
                    <div className="px-3 py-3 text-[12px] text-[#4c4c50]">
                      {sceneText ||
                        activeDetail ||
                        "Preparing Google Sheets tracker and writing execution roadmap."}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          {!sheetsFrameUrl ? (
            <div className="pointer-events-none absolute right-3 bottom-3 w-[min(42%,440px)] rounded-lg border border-black/[0.08] bg-white/90 px-3 py-2 shadow-[0_8px_18px_-16px_rgba(0,0,0,0.55)] backdrop-blur-sm">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">
                Live sheet typing
              </p>
              <div className="mt-1.5 max-h-[132px] overflow-y-auto rounded-md border border-black/[0.06] bg-white px-2.5 py-2 text-[12px] leading-[1.5] text-[#1f1f22]">
                {sheetPreviewRows.length ? (
                  <div className="space-y-1">
                    {sheetPreviewRows.map((row, index) => (
                      <p key={`sheet-stream-${index}`} className="line-clamp-2">
                        {row}
                      </p>
                    ))}
                    <span className="inline-block h-[12px] w-[1px] animate-pulse bg-[#1f1f22]" />
                  </div>
                ) : (
                  <p>
                    {sheetStatusLine || "Writing roadmap rows to Google Sheets..."}
                    <span className="ml-1 inline-block h-[12px] w-[1px] animate-pulse bg-[#1f1f22]" />
                  </p>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export { SheetsScene };
