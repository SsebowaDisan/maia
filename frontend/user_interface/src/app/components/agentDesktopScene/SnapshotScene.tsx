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
      </div>
    </div>
  );
}

export { SnapshotScene };
