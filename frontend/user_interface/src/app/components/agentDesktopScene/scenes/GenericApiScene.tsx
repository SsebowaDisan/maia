import type { ApiSceneState } from "../api_scene_state";

type GenericApiSceneProps = {
  activeTitle: string;
  state: ApiSceneState;
};

function statusTone(status: string): string {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "failed") {
    return "border-[#f1b7b7] bg-[#fff5f5] text-[#9a2323]";
  }
  if (normalized === "completed" || normalized === "success") {
    return "border-[#bfd9c3] bg-[#f3fbf4] text-[#245437]";
  }
  return "border-[#d2d2d7] bg-[#f5f5f7] text-[#3a3a3c]";
}

function validationTone(status: "passed" | "failed" | "pending"): string {
  if (status === "failed") {
    return "border-[#f1b7b7] bg-[#fff5f5] text-[#9a2323]";
  }
  if (status === "passed") {
    return "border-[#bfd9c3] bg-[#f3fbf4] text-[#245437]";
  }
  return "border-[#d2d2d7] bg-[#f5f5f7] text-[#3a3a3c]";
}

const SCENE_FAMILY_LABELS: Record<string, string> = {
  email: "Email",
  sheet: "Spreadsheet",
  document: "Document",
  chat: "Chat",
  crm: "CRM",
  support: "Support",
  commerce: "Commerce",
  browser: "Browser",
  api: "API",
};

function sceneFamilyLabel(family: string): string {
  return SCENE_FAMILY_LABELS[family] || "API";
}

function GenericApiScene({ activeTitle, state }: GenericApiSceneProps) {
  const theatreLabel = `${sceneFamilyLabel(state.sceneFamily)} theatre`;

  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_24%,rgba(80,129,255,0.12),rgba(6,10,18,0.95)_62%)] px-5 py-4 text-white">
      <div className="mx-auto flex h-full w-full max-w-[900px] flex-col gap-4 rounded-2xl border border-white/15 bg-[#0f1322]/90 p-4 backdrop-blur-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.1em] text-white/65">{theatreLabel}</p>
            <h3 className="mt-1 text-[20px] font-semibold text-white">
              {activeTitle || state.operationLabel || "Executing API operation"}
            </h3>
            <p className="mt-1 text-[13px] text-white/80">
              {state.summaryText || "Resolving connector action, object updates, and validation checks."}
            </p>
          </div>
          <div className={`rounded-full border px-3 py-1 text-[12px] font-semibold ${statusTone(state.statusLabel)}`}>
            {state.statusLabel || "in_progress"}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-white/12 bg-white/5 p-3">
            <p className="text-[11px] uppercase tracking-[0.08em] text-white/55">Connector</p>
            <p className="mt-1 text-[14px] font-medium text-white">{state.connectorLabel || state.connectorId || "API"}</p>
            {state.connectorId && state.connectorLabel !== state.connectorId ? (
              <p className="text-[11px] text-white/65">{state.connectorId}</p>
            ) : null}
          </div>
          <div className="rounded-xl border border-white/12 bg-white/5 p-3">
            <p className="text-[11px] uppercase tracking-[0.08em] text-white/55">Object</p>
            <p className="mt-1 text-[14px] font-medium text-white">{state.objectType || "record"}</p>
            <p className="text-[11px] text-white/65">{state.objectId || "pending id"}</p>
          </div>
          <div className="rounded-xl border border-white/12 bg-white/5 p-3">
            <p className="text-[11px] uppercase tracking-[0.08em] text-white/55">Operation</p>
            <p className="mt-1 text-[14px] font-medium text-white">{state.operationLabel || "Execute action"}</p>
          </div>
        </div>

        {state.fieldDiffs.length ? (
          <div className="rounded-xl border border-white/12 bg-white/5 p-3">
            <p className="text-[12px] font-semibold text-white">Field diffs</p>
            <div className="mt-2 space-y-2">
              {state.fieldDiffs.map((diff) => (
                <div key={`${diff.field}-${diff.fromValue}-${diff.toValue}`} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-[12px]">
                  <p className="font-medium text-white">{diff.field}</p>
                  <p className="mt-1 text-white/70">
                    {diff.fromValue || "empty"} {"->"} {diff.toValue || "empty"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {state.validations.length ? (
          <div className="rounded-xl border border-white/12 bg-white/5 p-3">
            <p className="text-[12px] font-semibold text-white">Validation state</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {state.validations.map((item) => (
                <div key={`${item.label}-${item.status}`} className={`rounded-full border px-3 py-1 text-[11px] ${validationTone(item.status)}`}>
                  {item.label}: {item.status}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {state.approvalRequired ? (
          <div className="rounded-xl border border-[#f1cd8a] bg-[#2f2614] px-3 py-2 text-[12px] text-[#f6d49b]">
            Approval required before commit. {state.approvalReason || "Review changes and confirm to continue."}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export { GenericApiScene };
