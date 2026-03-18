import type { ApiSceneState } from "../api_scene_state";

type ConnectorCloneSceneVariant =
  | "gmail"
  | "outlook"
  | "sheets"
  | "excel"
  | "slack"
  | "sap";

type ConnectorCloneSceneProps = {
  activeTitle: string;
  state: ApiSceneState;
  variant: ConnectorCloneSceneVariant;
};

type ScenePalette = {
  shellGradient: string;
  cardBg: string;
  cardBorder: string;
  textPrimary: string;
  textSecondary: string;
  accentBg: string;
  accentText: string;
};

type SceneDescriptor = {
  brand: string;
  theatreLabel: string;
  objectLabel: string;
  actionVerb: string;
};

const PALETTES: Record<ConnectorCloneSceneVariant, ScenePalette> = {
  gmail: {
    shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(239,68,68,0.24),rgba(17,24,39,0.95)_56%)]",
    cardBg: "bg-white/90",
    cardBorder: "border-[#fecaca]",
    textPrimary: "text-[#111827]",
    textSecondary: "text-[#6b7280]",
    accentBg: "bg-[#ef4444]/15",
    accentText: "text-[#991b1b]",
  },
  outlook: {
    shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(37,99,235,0.24),rgba(17,24,39,0.95)_56%)]",
    cardBg: "bg-white/90",
    cardBorder: "border-[#bfdbfe]",
    textPrimary: "text-[#0f172a]",
    textSecondary: "text-[#64748b]",
    accentBg: "bg-[#2563eb]/15",
    accentText: "text-[#1e3a8a]",
  },
  sheets: {
    shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(22,163,74,0.24),rgba(10,15,26,0.95)_58%)]",
    cardBg: "bg-[#f8fffb]/95",
    cardBorder: "border-[#bbf7d0]",
    textPrimary: "text-[#052e16]",
    textSecondary: "text-[#166534]",
    accentBg: "bg-[#16a34a]/15",
    accentText: "text-[#14532d]",
  },
  excel: {
    shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(5,150,105,0.24),rgba(9,14,23,0.95)_58%)]",
    cardBg: "bg-[#f4fffb]/95",
    cardBorder: "border-[#99f6e4]",
    textPrimary: "text-[#022c22]",
    textSecondary: "text-[#0f766e]",
    accentBg: "bg-[#059669]/15",
    accentText: "text-[#064e3b]",
  },
  slack: {
    shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(192,38,211,0.24),rgba(17,24,39,0.96)_60%)]",
    cardBg: "bg-white/90",
    cardBorder: "border-[#f5d0fe]",
    textPrimary: "text-[#111827]",
    textSecondary: "text-[#6b7280]",
    accentBg: "bg-[#c026d3]/15",
    accentText: "text-[#86198f]",
  },
  sap: {
    shellGradient: "bg-[radial-gradient(circle_at_20%_20%,rgba(2,132,199,0.24),rgba(11,19,32,0.96)_58%)]",
    cardBg: "bg-white/90",
    cardBorder: "border-[#bae6fd]",
    textPrimary: "text-[#0c4a6e]",
    textSecondary: "text-[#0369a1]",
    accentBg: "bg-[#0284c7]/15",
    accentText: "text-[#075985]",
  },
};

const DESCRIPTORS: Record<ConnectorCloneSceneVariant, SceneDescriptor> = {
  gmail: {
    brand: "Gmail",
    theatreLabel: "Mail theatre",
    objectLabel: "Thread",
    actionVerb: "Composing and synchronizing mail updates",
  },
  outlook: {
    brand: "Outlook",
    theatreLabel: "Mailbox theatre",
    objectLabel: "Message",
    actionVerb: "Applying mailbox operation",
  },
  sheets: {
    brand: "Google Sheets",
    theatreLabel: "Spreadsheet theatre",
    objectLabel: "Sheet row",
    actionVerb: "Writing spreadsheet changes",
  },
  excel: {
    brand: "Excel",
    theatreLabel: "Workbook theatre",
    objectLabel: "Workbook row",
    actionVerb: "Updating workbook values",
  },
  slack: {
    brand: "Slack",
    theatreLabel: "Channel theatre",
    objectLabel: "Message",
    actionVerb: "Publishing team communication",
  },
  sap: {
    brand: "SAP",
    theatreLabel: "ERP theatre",
    objectLabel: "Business document",
    actionVerb: "Applying enterprise transaction",
  },
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

function compactDiffPreview(state: ApiSceneState): string {
  if (!state.fieldDiffs.length) {
    return "No structured field diffs were emitted for this step.";
  }
  const [first] = state.fieldDiffs;
  return `${first.field}: ${first.fromValue || "empty"} -> ${first.toValue || "empty"}`;
}

function ConnectorCloneScene({
  activeTitle,
  state,
  variant,
}: ConnectorCloneSceneProps) {
  const palette = PALETTES[variant];
  const descriptor = DESCRIPTORS[variant];
  const headerTitle = activeTitle || state.operationLabel || descriptor.actionVerb;
  const objectValue = state.objectId || state.objectType || "pending";

  return (
    <div className={`absolute inset-0 px-5 py-4 ${palette.shellGradient}`}>
      <div className={`mx-auto flex h-full w-full max-w-[920px] flex-col gap-4 rounded-2xl border ${palette.cardBorder} ${palette.cardBg} p-4 shadow-[0_16px_48px_rgba(2,6,23,0.35)]`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className={`text-[11px] uppercase tracking-[0.11em] ${palette.textSecondary}`}>
              {descriptor.brand} {descriptor.theatreLabel}
            </p>
            <h3 className={`mt-1 text-[21px] font-semibold ${palette.textPrimary}`}>
              {headerTitle}
            </h3>
            <p className={`mt-1 text-[13px] ${palette.textSecondary}`}>
              {state.summaryText || descriptor.actionVerb}
            </p>
          </div>
          <div className={`rounded-full border px-3 py-1 text-[12px] font-semibold ${statusTone(state.statusLabel)}`}>
            {state.statusLabel || "in_progress"}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className={`rounded-xl border ${palette.cardBorder} bg-white/85 p-3`}>
            <p className={`text-[11px] uppercase tracking-[0.09em] ${palette.textSecondary}`}>Connector</p>
            <p className={`mt-1 text-[14px] font-semibold ${palette.textPrimary}`}>
              {state.connectorLabel || descriptor.brand}
            </p>
          </div>
          <div className={`rounded-xl border ${palette.cardBorder} bg-white/85 p-3`}>
            <p className={`text-[11px] uppercase tracking-[0.09em] ${palette.textSecondary}`}>{descriptor.objectLabel}</p>
            <p className={`mt-1 text-[14px] font-semibold ${palette.textPrimary}`}>{objectValue}</p>
          </div>
          <div className={`rounded-xl border ${palette.cardBorder} bg-white/85 p-3`}>
            <p className={`text-[11px] uppercase tracking-[0.09em] ${palette.textSecondary}`}>Operation</p>
            <p className={`mt-1 text-[14px] font-semibold ${palette.textPrimary}`}>
              {state.operationLabel || descriptor.actionVerb}
            </p>
          </div>
        </div>

        <div className={`rounded-xl border ${palette.cardBorder} ${palette.accentBg} px-3 py-2 text-[12px] font-medium ${palette.accentText}`}>
          {compactDiffPreview(state)}
        </div>

        {state.validations.length ? (
          <div className={`rounded-xl border ${palette.cardBorder} bg-white/85 p-3`}>
            <p className={`text-[12px] font-semibold ${palette.textPrimary}`}>Validation checks</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {state.validations.map((validation) => (
                <span
                  key={`${validation.label}-${validation.status}`}
                  className="rounded-full border border-black/10 bg-white px-3 py-1 text-[11px] font-medium text-[#374151]"
                >
                  {validation.label}: {validation.status}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {state.approvalRequired ? (
          <div className="rounded-xl border border-[#f1cd8a] bg-[#fff7e8] px-3 py-2 text-[12px] text-[#8a5a04]">
            Approval required before commit. {state.approvalReason || "Review changes and continue."}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export type { ConnectorCloneSceneVariant };
export { ConnectorCloneScene };
