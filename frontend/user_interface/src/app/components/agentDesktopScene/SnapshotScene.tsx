import { useEffect, useState } from "react";

type SnapshotSceneProps = {
  activeDetail: string;
  activeTitle: string;
  isBrowserScene: boolean;
  onSnapshotError?: () => void;
  sceneText: string;
  snapshotUrl: string;
};

function SnapshotScene({
  activeDetail,
  activeTitle,
  isBrowserScene,
  onSnapshotError,
  sceneText,
  snapshotUrl,
}: SnapshotSceneProps) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(false);
  }, [snapshotUrl]);

  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_8%,rgba(168,216,255,0.92),rgba(122,176,244,0.72)_40%,rgba(98,148,232,0.9)_100%)] p-9 text-[#1d1d1f]">
      <div className="relative mx-auto flex h-full w-full max-w-[840px] flex-col overflow-hidden rounded-[20px] border border-black/[0.1] bg-[#fcfcfd] shadow-[0_26px_58px_-42px_rgba(0,0,0,0.52)]">
        <div className="relative z-10 flex items-center gap-2 border-b border-black/[0.08] px-5 py-3">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <span className="ml-2 text-[12px] font-semibold tracking-[0.01em] text-[#3a3a3c]">
            {activeTitle || (isBrowserScene ? "Website capture" : "Live capture")}
          </span>
          <span className="ml-auto rounded-full border border-black/[0.1] bg-[#f7f8fb] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#5f6368]">
            {ready ? "Ready" : "Loading"}
          </span>
        </div>
        <div className="relative min-h-0 flex-1 overflow-hidden bg-[#f5f7fb]">
          {!ready ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-[50%] space-y-2 opacity-50">
                <div className="h-2 animate-pulse rounded-full bg-black/10" />
                <div className="h-2 w-[80%] animate-pulse rounded-full bg-black/8" />
                <div className="h-2 w-[90%] animate-pulse rounded-full bg-black/10" />
              </div>
            </div>
          ) : null}
          <img
            key={snapshotUrl}
            src={snapshotUrl}
            alt="Agent scene snapshot"
            className={`absolute inset-0 h-full w-full object-contain bg-[#f5f7fb] transition-opacity duration-150 ${ready ? "opacity-100" : "opacity-0"}`}
            onLoad={() => setReady(true)}
            onError={() => {
              setReady(false);
              onSnapshotError?.();
            }}
          />
          <div className="pointer-events-none absolute left-3 right-3 bottom-3 rounded-xl border border-black/[0.12] bg-white/92 px-3 py-2">
            <p className="line-clamp-2 text-[11px] text-[#3a3a3d]">
              {sceneText ||
                activeDetail ||
                (isBrowserScene
                  ? "Inspecting website and extracting evidence."
                  : "Running live agent action.")}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export { SnapshotScene };
