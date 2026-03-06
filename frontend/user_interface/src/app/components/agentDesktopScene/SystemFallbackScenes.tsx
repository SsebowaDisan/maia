type SystemSceneProps = {
  activeEventType: string;
  activeDetail: string;
  activeTitle: string;
  sceneText: string;
};

function isPlannerNarrativeEventType(eventType: string): boolean {
  const normalized = String(eventType || "").trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return (
    normalized === "planning_started" ||
    normalized.startsWith("plan_") ||
    normalized.startsWith("planning_") ||
    normalized.startsWith("task_understanding_") ||
    normalized.startsWith("preflight_") ||
    normalized.startsWith("llm.task_") ||
    normalized.startsWith("llm.plan_") ||
    normalized === "llm.web_routing_decision" ||
    normalized === "llm.intent_tags"
  );
}

function SystemScene({ activeEventType, activeDetail, activeTitle, sceneText }: SystemSceneProps) {
  const suppressPlannerNarrative = isPlannerNarrativeEventType(activeEventType);
  const narrativeText = suppressPlannerNarrative
    ? "Coordinating plan and execution handoff..."
    : sceneText || activeDetail || "Finalizing run events and preparing delivery output.";

  return (
    <div className="absolute inset-0 flex items-center justify-center bg-[radial-gradient(circle_at_50%_35%,rgba(255,255,255,0.08),rgba(7,9,12,0.96)_62%)] px-6">
      <div className="w-full max-w-[680px] rounded-2xl border border-white/15 bg-black/45 p-5 backdrop-blur-sm">
        <p className="text-[11px] uppercase tracking-[0.1em] text-white/60">System activity</p>
        <p className="mt-1 text-[20px] font-semibold text-white">
          {activeTitle || "Processing secure agent workflow"}
        </p>
        <p className="mt-2 text-[13px] text-white/80">
          {narrativeText}
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
