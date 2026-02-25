type AgentDesktopSceneProps = {
  snapshotUrl: string;
  isBrowserScene: boolean;
  isEmailScene: boolean;
  isDocumentScene: boolean;
  isSystemScene: boolean;
  canRenderPdfFrame: boolean;
  stageFileUrl: string;
  stageFileName: string;
  browserUrl: string;
  emailRecipient: string;
  emailSubject: string;
  emailBodyHint: string;
  sceneText: string;
  activeTitle: string;
  activeDetail: string;
  activeEventType: string;
  activeSceneData: Record<string, unknown>;
  onSnapshotError?: () => void;
};

export function AgentDesktopScene({
  snapshotUrl,
  isBrowserScene,
  isEmailScene,
  isDocumentScene,
  isSystemScene,
  canRenderPdfFrame,
  stageFileUrl,
  stageFileName,
  browserUrl,
  emailRecipient,
  emailSubject,
  emailBodyHint,
  sceneText,
  activeTitle,
  activeDetail,
  activeEventType,
  activeSceneData,
  onSnapshotError,
}: AgentDesktopSceneProps) {
  const keywordBadges = Array.isArray(activeSceneData["keywords"])
    ? activeSceneData["keywords"]
        .map((item) => String(item || "").trim())
        .filter((item) => item)
        .slice(0, 6)
    : [];
  const clipboardPreview = typeof activeSceneData["clipboard_text"] === "string"
    ? activeSceneData["clipboard_text"]
    : "";

  if (snapshotUrl) {
    return (
      <div className="absolute inset-0">
        <img
          src={snapshotUrl}
          alt="Agent scene snapshot"
          className="absolute inset-0 h-full w-full object-cover"
          onError={onSnapshotError}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/15 to-black/20" />
        <div className="absolute left-3 right-3 top-3 rounded-xl border border-white/20 bg-black/45 px-3 py-2 text-white backdrop-blur-sm">
          <p className="text-[12px] font-semibold">
            {activeTitle || (isBrowserScene ? "Live browser capture" : "Live scene capture")}
          </p>
          <p className="mt-0.5 line-clamp-2 text-[11px] text-white/85">
            {sceneText ||
              activeDetail ||
              (isBrowserScene
                ? "Inspecting website and extracting evidence."
                : "Running live agent action.")}
          </p>
          {keywordBadges.length ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {keywordBadges.map((keyword) => (
                <span
                  key={keyword}
                  className="rounded-full border border-white/25 bg-white/10 px-2 py-0.5 text-[10px] text-white/90"
                >
                  {keyword}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  if (isBrowserScene) {
    const canRenderLiveUrl =
      browserUrl.startsWith("http://") || browserUrl.startsWith("https://");
    return (
      <div className="absolute inset-0 flex flex-col bg-[#0d1118] text-white/90">
        <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <div className="ml-2 flex-1 truncate rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[11px] text-white/85">
            {browserUrl || "Searching the web and opening result pages..."}
          </div>
        </div>
        {canRenderLiveUrl ? (
          <div className="relative flex-1 bg-white">
            <iframe
              src={browserUrl}
              title="Live website preview"
              className="h-full w-full border-0"
              sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
              referrerPolicy="no-referrer-when-downgrade"
            />
            <div className="pointer-events-none absolute inset-x-3 top-3 rounded-xl border border-black/10 bg-white/80 px-3 py-2 text-[#1d1d1f] backdrop-blur-sm">
              <p className="text-[12px] font-semibold">
                {activeTitle || "Live website preview"}
              </p>
              <p className="mt-0.5 line-clamp-2 text-[11px] text-[#3a3a3c]">
                {sceneText || activeDetail || "Opening and reviewing the website in real time."}
              </p>
              {keywordBadges.length ? (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {keywordBadges.map((keyword) => (
                    <span
                      key={keyword}
                      className="rounded-full border border-black/10 bg-white/70 px-2 py-0.5 text-[10px] text-[#1d1d1f]"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="flex-1 space-y-3 p-4">
            <p className="text-[13px] font-semibold text-white">{activeTitle || "Browser scene"}</p>
            <p className="text-[12px] text-white/80">
              {sceneText || activeDetail || "Inspecting page content and extracting evidence..."}
            </p>
            <div className="space-y-2">
              <div className="h-2 w-[92%] rounded-full bg-white/20" />
              <div className="h-2 w-[84%] rounded-full bg-white/15" />
              <div className="h-2 w-[88%] rounded-full bg-white/20" />
              <div className="h-2 w-[63%] rounded-full bg-white/15" />
            </div>
          </div>
        )}
      </div>
    );
  }

  if (isEmailScene) {
    return (
      <div className="absolute inset-0 flex flex-col bg-[#12161d] text-white/90">
        <div className="border-b border-white/10 px-3 py-2 text-[12px] font-medium">Gmail compose</div>
        <div className="space-y-2 p-3 text-[11px]">
          <div className="rounded-lg border border-white/15 bg-white/5 px-2.5 py-2">
            <span className="text-white/65">To:</span> <span className="text-white">{emailRecipient}</span>
          </div>
          <div className="rounded-lg border border-white/15 bg-white/5 px-2.5 py-2">
            <span className="text-white/65">Subject:</span> <span className="text-white">{emailSubject}</span>
          </div>
          <div className="min-h-[120px] rounded-lg border border-white/15 bg-white/5 px-2.5 py-2 text-white/85">
            {emailBodyHint}
          </div>
          {activeEventType === "email_click_send" ? (
            <div className="rounded-lg border border-white/20 bg-white/10 px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-white">
              Send action confirmed
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  if (isDocumentScene && canRenderPdfFrame) {
    return (
      <iframe
        src={`${stageFileUrl}#toolbar=0&navpanes=0&scrollbar=0`}
        title="Agent PDF live preview"
        className="absolute inset-0 h-full w-full bg-white"
      />
    );
  }

  if (isDocumentScene) {
    return (
      <div className="absolute inset-0 px-4 py-3 text-white/85">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[12px] font-medium">{stageFileName}</span>
          <span className="text-[10px] uppercase tracking-[0.08em] text-white/65">editing</span>
        </div>
        <p className="mb-3 text-[11px] text-white/85">
          {sceneText || activeDetail || "Preparing and updating document blocks..."}
        </p>
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

  if (isSystemScene) {
    return (
      <div className="absolute inset-0 flex items-center justify-center bg-[radial-gradient(circle_at_50%_35%,rgba(255,255,255,0.08),rgba(7,9,12,0.96)_62%)] px-6">
        <div className="w-full max-w-[680px] rounded-2xl border border-white/15 bg-black/45 p-5 backdrop-blur-sm">
          <p className="text-[11px] uppercase tracking-[0.1em] text-white/60">System activity</p>
          <p className="mt-1 text-[20px] font-semibold text-white">
            {activeTitle || "Processing secure agent workflow"}
          </p>
          <p className="mt-2 text-[13px] text-white/80">
            {sceneText || activeDetail || "Finalizing run events and preparing delivery output."}
          </p>
          <div className="mt-4 space-y-2">
            <div className="h-2 w-[92%] rounded-full bg-white/25" />
            <div className="h-2 w-[86%] rounded-full bg-white/18" />
            <div className="h-2 w-[95%] rounded-full bg-white/25" />
            <div className="h-2 w-[78%] rounded-full bg-white/18" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="absolute inset-0 px-4 py-3 text-white/85">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[12px] font-medium">{stageFileName}</span>
        <span className="text-[10px] uppercase tracking-[0.08em] text-white/65">
          {isSystemScene ? "system" : "reading"}
        </span>
      </div>
      <div className="space-y-2">
        <div className="h-2 w-[88%] rounded-full bg-white/15" />
        <div className="h-2 w-[74%] rounded-full bg-white/10" />
        <div className="h-2 w-[91%] rounded-full bg-white/15" />
        <div className="h-2 w-[82%] rounded-full bg-white/10" />
        <div className="h-2 w-[66%] rounded-full bg-white/15" />
        <div className="h-2 w-[92%] rounded-full bg-white/10" />
      </div>
    </div>
  );
}
