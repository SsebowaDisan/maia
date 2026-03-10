type SystemSceneProps = {
  activeEventType: string;
  activeDetail: string;
  activeTitle: string;
  sceneText: string;
};

function SystemScene({ activeEventType, activeDetail, activeTitle, sceneText }: SystemSceneProps) {
  const normalizedType = String(activeEventType || "").trim().toLowerCase();
  const narrativeText =
    sceneText ||
    activeDetail ||
    (normalizedType === "approval_required"
      ? "Waiting for your approval before continuing."
      : "Coordinating execution state and preparing next action.");

  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_18%,rgba(152,182,229,0.22),transparent_40%),#0b1017] px-6 py-8">
      <div className="relative z-10 flex h-full items-center justify-center">
        <div className="w-full max-w-[720px] rounded-[24px] border border-[#2b3342] bg-[#111827] p-7 shadow-[0_24px_60px_-40px_rgba(6,11,20,0.9)]">
          <div className="mb-5 h-[3px] w-[140px] rounded-full bg-[linear-gradient(90deg,#7aa2e6,#95c6ff,#c2ddff)]" />
          <div className="mb-4 flex items-center justify-between gap-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/55">System activity</p>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-[#0f1726] px-2.5 py-1 text-[10px] font-medium text-white/65">
              <span className="h-1.5 w-1.5 rounded-full bg-[#34c759]" />
              Live
            </span>
          </div>
          <p className="text-[clamp(28px,3.3vw,42px)] font-semibold leading-[1.08] tracking-[-0.02em] text-[#f3f4f7]">
            {activeTitle || "Processing secure agent workflow"}
          </p>
          <p className="mt-3 text-[15px] leading-[1.5] text-white/72">
            {narrativeText}
          </p>
          <div className="mt-6 overflow-hidden rounded-full border border-white/10 bg-[#0d1420] p-[2px]">
            <div className="h-[6px] w-[68%] rounded-full bg-[linear-gradient(90deg,#8fb7ff,#a7d0ff)]" />
          </div>
          <div className="mt-5 space-y-3">
            <div className="h-2 w-[90%] rounded-full bg-white/18" />
            <div className="h-2 w-[84%] rounded-full bg-white/14" />
            <div className="h-2 w-[94%] rounded-full bg-white/18" />
            <div className="h-2 w-[78%] rounded-full bg-white/14" />
          </div>
        </div>
      </div>
    </div>
  );
}

type DefaultSceneProps = {
  isSystemScene: boolean;
  stageFileName: string;
};

function DefaultScene({ isSystemScene, stageFileName }: DefaultSceneProps) {
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

export { DefaultScene, SystemScene };
