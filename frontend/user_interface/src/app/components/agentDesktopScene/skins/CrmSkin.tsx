import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, FieldDiffsList, InfoCell, SkinHeader, SkinShell, ToolParamsPreview, ValidationBadges } from "./shared";

/** Salesforce / HubSpot — record card with fields grid and pipeline stage. */
function CrmSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} subtitle={state.summaryText} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <InfoCell label="Record type" value={state.objectType || "Contact"} palette={palette} />
        <InfoCell label="Record ID" value={state.objectId || "pending"} palette={palette} />
        <InfoCell label="Operation" value={state.operationLabel || descriptor.actionVerb} palette={palette} />
      </div>

      {/* Pipeline stage indicator */}
      <div className={`flex items-center gap-1 rounded-xl ${palette.accentBg} px-3 py-2`}>
        {["Lead", "Qualified", "Proposal", "Negotiation", "Won"].map((stage, i) => (
          <div
            key={stage}
            className={`flex-1 rounded-md py-1.5 text-center text-[11px] font-medium transition-all ${
              i <= 2 ? `${palette.accentBg} ${palette.accentText} border border-current/20` : `opacity-30 ${palette.textSecondary}`
            }`}
          >
            {stage}
          </div>
        ))}
      </div>

      <ToolParamsPreview
        data={data}
        palette={palette}
        fields={[
          { key: "email", label: "Email" },
          { key: "first_name", label: "First name" },
          { key: "last_name", label: "Last name" },
          { key: "company", label: "Company" },
          { key: "deal_name", label: "Deal" },
          { key: "amount", label: "Amount" },
          { key: "stage", label: "Stage" },
        ]}
      />

      <FieldDiffsList diffs={state.fieldDiffs} palette={palette} />
      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { CrmSkin };
